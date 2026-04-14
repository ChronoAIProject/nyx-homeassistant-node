#!/command/with-contenv bashio
# ==============================================================================
# NyxID Node Add-on — Setup (runs on every start)
# ==============================================================================

NYXID_CONFIG="/data/nyxid-node"
SERVICES_FILE="/data/configured-services.txt"

mkdir -p "${NYXID_CONFIG}"

# --------------------------------------------------------------------------
# 1. Node registration (first run only)
# --------------------------------------------------------------------------
if [ ! -f "${NYXID_CONFIG}/config.toml" ] || ! grep -q '\[node\]' "${NYXID_CONFIG}/config.toml" 2>/dev/null; then
    server_url=$(bashio::config 'nyxid_server_url')
    reg_token=$(bashio::config 'registration_token')

    if bashio::var.is_empty "${reg_token}"; then
        bashio::log.fatal "Node is not registered and no registration token is configured."
        bashio::log.fatal "Please set 'registration_token' in the add-on configuration."
        exit 1
    fi

    if bashio::var.is_empty "${server_url}"; then
        bashio::log.fatal "NyxID server URL is not configured."
        bashio::log.fatal "Please set 'nyxid_server_url' in the add-on configuration."
        exit 1
    fi

    node_name=$(bashio::config 'node_name')
    bashio::log.info "Registering node '${node_name}' with NyxID server at ${server_url}..."

    if ! nyxid node register \
        --token "${reg_token}" \
        --url "${server_url}" \
        --config "${NYXID_CONFIG}"; then
        bashio::log.fatal "Node registration failed. Check your registration token and server URL."
        exit 1
    fi

    bashio::log.info "Node registered successfully."
fi

# --------------------------------------------------------------------------
# 2. Determine desired service slugs
# --------------------------------------------------------------------------
desired_slugs="homeassistant"

for index in $(bashio::config 'services|keys'); do
    slug=$(bashio::config "services[${index}].slug")
    desired_slugs="${desired_slugs} ${slug}"
done

# --------------------------------------------------------------------------
# 3. Remove stale services
# --------------------------------------------------------------------------
if [ -f "${SERVICES_FILE}" ]; then
    while IFS= read -r old_slug; do
        [ -z "${old_slug}" ] && continue
        found=false
        for desired in ${desired_slugs}; do
            if [ "${desired}" = "${old_slug}" ]; then
                found=true
                break
            fi
        done
        if [ "${found}" = "false" ]; then
            bashio::log.info "Removing stale service credential: ${old_slug}"
            nyxid node credentials --config "${NYXID_CONFIG}" remove \
                --service "${old_slug}" || true
        fi
    done < "${SERVICES_FILE}"
fi

# --------------------------------------------------------------------------
# 4. Update Home Assistant built-in credential (every start)
# --------------------------------------------------------------------------
bashio::log.info "Updating Home Assistant API credential..."

nyxid node credentials --config "${NYXID_CONFIG}" add \
    --service "homeassistant" \
    --header "Authorization" \
    --secret-format bearer \
    --value "${SUPERVISOR_TOKEN}" \
    --url "http://supervisor/core/api"

# --------------------------------------------------------------------------
# 5. Sync additional services from options
# --------------------------------------------------------------------------
for index in $(bashio::config 'services|keys'); do
    slug=$(bashio::config "services[${index}].slug")
    target_url=$(bashio::config "services[${index}].target_url")
    cred_type=$(bashio::config "services[${index}].credential_type")
    cred_name=$(bashio::config "services[${index}].credential_name")
    cred_value=$(bashio::config "services[${index}].credential_value")

    bashio::log.info "Configuring service: ${slug} → ${target_url}"

    if [ "${cred_type}" = "header" ]; then
        nyxid node credentials --config "${NYXID_CONFIG}" add \
            --service "${slug}" \
            --header "${cred_name}" \
            --secret-format raw \
            --value "${cred_value}" \
            --url "${target_url}"
    else
        nyxid node credentials --config "${NYXID_CONFIG}" add \
            --service "${slug}" \
            --query-param "${cred_name}" \
            --value "${cred_value}" \
            --url "${target_url}"
    fi
done

# --------------------------------------------------------------------------
# 6. Save current service list for next-run diff
# --------------------------------------------------------------------------
for slug in ${desired_slugs}; do
    echo "${slug}"
done > "${SERVICES_FILE}"

bashio::log.info "Setup complete."
