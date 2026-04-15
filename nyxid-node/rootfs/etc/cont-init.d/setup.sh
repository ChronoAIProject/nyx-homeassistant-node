#!/command/with-contenv bashio
# ==============================================================================
# NyxID Node Add-on — Setup (runs on every start)
# ==============================================================================

NYXID_CONFIG="/data/nyxid-node"
SERVICES_FILE="/data/configured-services.txt"
HA_SLUG_FILE="/data/ha-service-slug"
SETUP_DONE_FILE="/data/setup-done"

mkdir -p "${NYXID_CONFIG}"

# Derive REST API base URL from WebSocket URL
# wss://host/api/v1/nodes/ws → https://host
server_url=$(bashio::config 'nyxid_server_url')
api_base=$(echo "${server_url}" | sed 's|^wss://|https://|;s|^ws://|http://|;s|/api/v1/nodes/ws$||')
access_token=$(bashio::config 'nyxid_access_token')

# --------------------------------------------------------------------------
# 1. First-time setup: register node + create service (only once)
# --------------------------------------------------------------------------
if [ ! -f "${SETUP_DONE_FILE}" ]; then

    if bashio::var.is_empty "${access_token}"; then
        bashio::log.fatal "NyxID access token is required for initial setup."
        bashio::log.fatal "Get one from: nyxid api-key create --name ha-addon --scopes 'read write' --allow-all-nodes --allow-all-services"
        bashio::log.fatal "Or copy from: cat ~/.nyxid/access_token"
        exit 1
    fi

    # --- 1a. Create registration token via API ---
    if [ ! -f "${NYXID_CONFIG}/config.toml" ] || ! grep -q '\[node\]' "${NYXID_CONFIG}/config.toml" 2>/dev/null; then
        node_name=$(bashio::config 'node_name')
        bashio::log.info "Creating registration token for '${node_name}'..."

        reg_response=$(curl -sf -X POST "${api_base}/api/v1/nodes/register-token" \
            -H "Authorization: Bearer ${access_token}" \
            -H "Content-Type: application/json" \
            -d "{\"name\":\"${node_name}\"}")

        reg_token=$(echo "${reg_response}" | jq -r '.token // empty')

        if [ -z "${reg_token}" ]; then
            bashio::log.fatal "Failed to create registration token: ${reg_response}"
            exit 1
        fi

        # --- 1b. Register node ---
        bashio::log.info "Registering node '${node_name}'..."

        if ! nyxid node register \
            --token "${reg_token}" \
            --url "${server_url}" \
            --config "${NYXID_CONFIG}"; then
            bashio::log.fatal "Node registration failed."
            exit 1
        fi

        bashio::log.info "Node registered successfully."
    fi

    # --- 1c. Create HA service with exact slug via API ---
    node_id=$(grep '^id' "${NYXID_CONFIG}/config.toml" | head -1 | sed 's/.*= *"\(.*\)"/\1/')
    ha_slug="homeassistant"

    bashio::log.info "Creating Home Assistant service (slug: ${ha_slug})..."

    svc_response=$(curl -sf -X POST "${api_base}/api/v1/keys" \
        -H "Authorization: Bearer ${access_token}" \
        -H "Content-Type: application/json" \
        -d "{
            \"label\": \"Home Assistant\",
            \"slug\": \"${ha_slug}\",
            \"endpoint_url\": \"http://supervisor/core/api\",
            \"auth_method\": \"none\",
            \"auth_key_name\": \"Authorization\",
            \"node_id\": \"${node_id}\"
        }")

    # Extract actual slug (may have -2, -3 suffix if "homeassistant" was taken)
    actual_slug=$(echo "${svc_response}" | jq -r '.slug // empty')

    if [ -n "${actual_slug}" ]; then
        echo "${actual_slug}" > "${HA_SLUG_FILE}"
        bashio::log.info "HA service created: ${actual_slug}"
    else
        bashio::log.error "Failed to create HA service: ${svc_response}"
        bashio::log.warning "Falling back to slug: ${ha_slug}"
        echo "${ha_slug}" > "${HA_SLUG_FILE}"
    fi

    touch "${SETUP_DONE_FILE}"
fi

# --------------------------------------------------------------------------
# 2. Determine HA credential slug (from saved file)
# --------------------------------------------------------------------------
if [ -f "${HA_SLUG_FILE}" ]; then
    ha_slug=$(cat "${HA_SLUG_FILE}")
else
    ha_slug="homeassistant"
fi

# --------------------------------------------------------------------------
# 3. Update Home Assistant credential (every start — token changes)
# --------------------------------------------------------------------------
bashio::log.info "Updating Home Assistant API credential (slug: ${ha_slug})..."

nyxid node credentials --config "${NYXID_CONFIG}" add \
    --service "${ha_slug}" \
    --header "Authorization" \
    --secret-format bearer \
    --value "${SUPERVISOR_TOKEN}" \
    --url "http://supervisor/core/api"

# --------------------------------------------------------------------------
# 4. Sync additional services from options
# --------------------------------------------------------------------------
desired_slugs="${ha_slug}"

for index in $(bashio::config 'services|keys'); do
    slug=$(bashio::config "services[${index}].slug")
    target_url=$(bashio::config "services[${index}].target_url")
    cred_type=$(bashio::config "services[${index}].credential_type")
    cred_name=$(bashio::config "services[${index}].credential_name")
    cred_value=$(bashio::config "services[${index}].credential_value")

    desired_slugs="${desired_slugs} ${slug}"
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
# 5. Remove stale services
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

# Save current service list
for slug in ${desired_slugs}; do
    echo "${slug}"
done > "${SERVICES_FILE}"

bashio::log.info "Setup complete."
