#!/command/with-contenv bashio
# ==============================================================================
# NyxID Node Add-on — Setup (runs on every start, each step is idempotent)
# ==============================================================================

NYXID_CONFIG="/data/nyxid-node"
SERVICES_FILE="/data/configured-services.txt"

mkdir -p "${NYXID_CONFIG}"

server_url=$(bashio::config 'nyxid_server_url')
api_base=$(echo "${server_url}" | sed 's|^wss://|https://|;s|^ws://|http://|;s|/api/v1/nodes/ws$||')
access_token=$(bashio::config 'nyxid_access_token')

# --------------------------------------------------------------------------
# 1. Node registration (skip if already registered)
# --------------------------------------------------------------------------
if [ ! -f "${NYXID_CONFIG}/config.toml" ] || ! grep -q '\[node\]' "${NYXID_CONFIG}/config.toml" 2>/dev/null; then

    if bashio::var.is_empty "${access_token}"; then
        bashio::log.fatal "NyxID access token is required."
        exit 1
    fi

    node_name=$(bashio::config 'node_name')
    bashio::log.info "Creating registration token for '${node_name}'..."

    reg_response=$(curl -sf -X POST "${api_base}/api/v1/nodes/register-token" \
        -H "Authorization: Bearer ${access_token}" \
        -H "Content-Type: application/json" \
        -d "{\"name\":\"${node_name}\"}")

    reg_token=$(echo "${reg_response}" | jq -r '.token // empty')

    if [ -z "${reg_token}" ]; then
        bashio::log.fatal "Failed to create registration token."
        exit 1
    fi

    bashio::log.info "Registering node..."
    if ! nyxid node register \
        --token "${reg_token}" \
        --url "${server_url}" \
        --config "${NYXID_CONFIG}"; then
        bashio::log.fatal "Node registration failed."
        exit 1
    fi

    node_id=$(grep '^id' "${NYXID_CONFIG}/config.toml" | head -1 | sed 's/.*= *"\(.*\)"/\1/')
    bashio::log.info "Node registered: ${node_id}"
fi

# --------------------------------------------------------------------------
# 2. Determine HA service slug
# --------------------------------------------------------------------------
ha_slug=$(bashio::config 'ha_service_slug')
node_id=$(grep '^id' "${NYXID_CONFIG}/config.toml" | head -1 | sed 's/.*= *"\(.*\)"/\1/')

if bashio::var.is_empty "${ha_slug}"; then
    bashio::log.warning "============================================"
    bashio::log.warning "No HA service slug configured."
    bashio::log.warning "Run this on your machine to create one:"
    bashio::log.warning ""
    bashio::log.warning "  nyxid service add --custom \\"
    bashio::log.warning "    --via-node ${node_id} \\"
    bashio::log.warning "    --endpoint-url 'http://supervisor/core/api' \\"
    bashio::log.warning "    --auth-method none"
    bashio::log.warning ""
    bashio::log.warning "Then paste the slug into the add-on config."
    bashio::log.warning "============================================"
else
    # Bind the service to this node (idempotent)
    if ! bashio::var.is_empty "${access_token}"; then
        nyxid service update "${ha_slug}" \
            --node-id "${node_id}" \
            --access-token "${access_token}" \
            --base-url "${api_base}" 2>/dev/null || true
    fi

    # Update credential (every start — SUPERVISOR_TOKEN changes)
    bashio::log.info "Updating Home Assistant credential (slug: ${ha_slug})..."
    nyxid node credentials --config "${NYXID_CONFIG}" add \
        --service "${ha_slug}" \
        --header "Authorization" \
        --secret-format bearer \
        --value "${SUPERVISOR_TOKEN}" \
        --url "http://supervisor/core/api"
fi

# --------------------------------------------------------------------------
# 3. Sync additional services from options
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
# 4. Remove stale services
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
            bashio::log.info "Removing stale credential: ${old_slug}"
            nyxid node credentials --config "${NYXID_CONFIG}" remove \
                --service "${old_slug}" || true
        fi
    done < "${SERVICES_FILE}"
fi

for slug in ${desired_slugs}; do
    echo "${slug}"
done > "${SERVICES_FILE}"

bashio::log.info "Setup complete."
