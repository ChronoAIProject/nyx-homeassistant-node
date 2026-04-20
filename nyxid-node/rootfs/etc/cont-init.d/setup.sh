#!/command/with-contenv bashio
# ==============================================================================
# NyxID Node Add-on — Setup (runs on every start, each step is idempotent)
# ==============================================================================

NYXID_CONFIG="/data/nyxid-node"
SERVICES_FILE="/data/configured-services.txt"
HA_STATE_FILE="/data/ha-service-id"

mkdir -p "${NYXID_CONFIG}"

server_url=$(bashio::config 'nyxid_server_url')
api_base=$(echo "${server_url}" | sed 's|^wss://|https://|;s|^ws://|http://|;s|/api/v1/nodes/ws$||')
api_key=$(bashio::config 'nyxid_api_key')

# --------------------------------------------------------------------------
# 1. Node registration (skip if already registered)
# --------------------------------------------------------------------------
if [ ! -f "${NYXID_CONFIG}/config.toml" ] || ! grep -q '\[node\]' "${NYXID_CONFIG}/config.toml" 2>/dev/null; then

    if bashio::var.is_empty "${api_key}"; then
        bashio::log.fatal "NyxID API key is required."
        bashio::log.fatal "Create one: nyxid api-key create --name ha-addon --scopes 'read write' --allow-all-nodes --allow-all-services"
        exit 1
    fi

    node_name=$(bashio::config 'node_name')
    bashio::log.info "Creating registration token for '${node_name}'..."

    reg_response=$(curl -sf -X POST "${api_base}/api/v1/nodes/register-token" \
        -H "Authorization: Bearer ${api_key}" \
        -H "Content-Type: application/json" \
        -d "{\"name\":\"${node_name}\"}")

    reg_token=$(echo "${reg_response}" | jq -r '.token // empty')

    if [ -z "${reg_token}" ]; then
        bashio::log.fatal "Failed to create registration token. Check your API key."
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

    bashio::log.info "Node registered successfully."
fi

node_id=$(grep '^id' "${NYXID_CONFIG}/config.toml" | head -1 | sed 's/.*= *"\(.*\)"/\1/')

# --------------------------------------------------------------------------
# 2. HA service — auto-provision (UUID-anchored)
#    Skipped entirely if ha_service_label is not configured (admin variant
#    inherits this script but doesn't provision an HA Core service).
# --------------------------------------------------------------------------
label=$(bashio::config 'ha_service_label')
# bashio returns the literal string "null" when the option key is missing
if [ -z "${label}" ] || [ "${label}" = "null" ]; then
    bashio::log.info "ha_service_label not set — skipping HA service provisioning."
    ha_slug=""
else

if bashio::var.is_empty "${api_key}"; then
    bashio::log.fatal "NyxID API key missing — cannot provision HA service."
    exit 1
fi

# Legacy migration: first line of SERVICES_FILE historically held the ha_slug.
if [ ! -f "${HA_STATE_FILE}" ] && [ -f "${SERVICES_FILE}" ]; then
    legacy_slug=$(head -1 "${SERVICES_FILE}" 2>/dev/null)
    if [ -n "${legacy_slug}" ]; then
        bashio::log.info "Migrating legacy HA slug '${legacy_slug}' to UUID-anchored state..."
        legacy_id=$(curl -sf -H "Authorization: Bearer ${api_key}" \
            "${api_base}/api/v1/keys" \
            | jq -r --arg s "${legacy_slug}" '.keys[] | select(.slug == $s) | .id' \
            | head -1)
        if [ -n "${legacy_id}" ]; then
            echo "${legacy_id}" > "${HA_STATE_FILE}"
            bashio::log.info "  Migrated to service id ${legacy_id}"
        fi
    fi
fi

# Try to reuse
ha_service_id=""
ha_slug=""
if [ -f "${HA_STATE_FILE}" ]; then
    saved_id=$(cat "${HA_STATE_FILE}")
    resp=$(curl -sf -H "Authorization: Bearer ${api_key}" \
        "${api_base}/api/v1/keys/${saved_id}" 2>/dev/null || echo "")
    if [ -n "${resp}" ]; then
        current_node=$(echo "${resp}" | jq -r '.node_id // empty')
        current_label=$(echo "${resp}" | jq -r '.label // empty')
        current_slug=$(echo "${resp}" | jq -r '.slug // empty')
        current_ctype=$(echo "${resp}" | jq -r '.credential_type // empty')
        if [ "${current_node}" = "${node_id}" ] && [ "${current_ctype}" = "node_managed" ]; then
            ha_service_id="${saved_id}"
            ha_slug="${current_slug}"
            bashio::log.info "Reusing existing HA service: ${ha_slug} (id ${ha_service_id})"
            if [ "${current_label}" != "${label}" ]; then
                bashio::log.info "  Label changed: '${current_label}' → '${label}'"
                curl -sf -X PUT -H "Authorization: Bearer ${api_key}" \
                    -H "Content-Type: application/json" \
                    -d "{\"label\": \"${label}\"}" \
                    "${api_base}/api/v1/keys/${ha_service_id}" >/dev/null || true
            fi
        else
            bashio::log.warning "Saved HA service mismatch — recreating."
            rm -f "${HA_STATE_FILE}"
        fi
    else
        bashio::log.warning "Saved HA service id not found on server — recreating."
        rm -f "${HA_STATE_FILE}"
    fi
fi

# Create if needed (single POST with bearer + node_id — NyxID #419 workaround)
if [ -z "${ha_service_id}" ]; then
    bashio::log.info "Creating HA service '${label}'..."
    create_resp=$(curl -sf -X POST \
        -H "Authorization: Bearer ${api_key}" \
        -H "Content-Type: application/json" \
        -d "{
            \"label\": \"${label}\",
            \"key_type\": \"http\",
            \"endpoint_url\": \"http://supervisor/core/api\",
            \"auth_method\": \"bearer\",
            \"auth_key_name\": \"Authorization\",
            \"node_id\": \"${node_id}\"
        }" \
        "${api_base}/api/v1/keys")
    if [ -z "${create_resp}" ]; then
        bashio::log.fatal "Failed to create HA service (empty response)."
        exit 1
    fi
    ha_service_id=$(echo "${create_resp}" | jq -r '.id // empty')
    ha_slug=$(echo "${create_resp}" | jq -r '.slug // empty')
    if [ -z "${ha_service_id}" ] || [ -z "${ha_slug}" ]; then
        bashio::log.fatal "HA service creation response missing id or slug: ${create_resp}"
        exit 1
    fi
    echo "${ha_service_id}" > "${HA_STATE_FILE}"
    bashio::log.info "  Created: ${ha_slug} (id ${ha_service_id})"
fi

# Push SUPERVISOR_TOKEN credential (every start — token rotates)
bashio::log.info "Pushing HA credential for ${ha_slug}..."
nyxid node credentials --config "${NYXID_CONFIG}" add \
    --service "${ha_slug}" \
    --header "Authorization" \
    --secret-format bearer \
    --value "${SUPERVISOR_TOKEN}" \
    --url "http://supervisor/core/api"

fi  # end of HA-service provisioning block

# --------------------------------------------------------------------------
# 3. Sync additional (user-defined) services
# --------------------------------------------------------------------------
user_slugs=""

for index in $(bashio::config 'services|keys'); do
    slug=$(bashio::config "services[${index}].slug")
    target_url=$(bashio::config "services[${index}].target_url")
    cred_type=$(bashio::config "services[${index}].credential_type")
    cred_name=$(bashio::config "services[${index}].credential_name")
    cred_value=$(bashio::config "services[${index}].credential_value")

    user_slugs="${user_slugs} ${slug}"
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
# 4. Remove stale user-service credentials (HA slug is tracked separately)
# --------------------------------------------------------------------------
if [ -f "${SERVICES_FILE}" ]; then
    while IFS= read -r old_slug; do
        [ -z "${old_slug}" ] && continue
        # Never touch the HA slug (it's tracked via HA_STATE_FILE)
        [ "${old_slug}" = "${ha_slug}" ] && continue
        found=false
        for desired in ${user_slugs}; do
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

# Track only user-defined slugs in SERVICES_FILE going forward
: > "${SERVICES_FILE}"
for slug in ${user_slugs}; do
    echo "${slug}" >> "${SERVICES_FILE}"
done

bashio::log.warning "============================================"
bashio::log.warning "Setup complete."
bashio::log.warning "  HA service slug: ${ha_slug}"
bashio::log.warning "  Call it with: nyxid proxy request ${ha_slug} states"
bashio::log.warning "============================================"
