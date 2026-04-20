#!/command/with-contenv bashio
# ==============================================================================
# NyxID Node (Admin) — Auto-provision Supervisor service on NyxID + push credential
# Runs AFTER the inherited setup.sh (lexicographic order: setup.sh < supervisor.sh)
# ==============================================================================

NYXID_CONFIG="/data/nyxid-node"
STATE_FILE="/data/supervisor-service-id"
LEGACY_SLUG_FILE="/data/last-supervisor-slug"

label=$(bashio::config 'supervisor_service_label')
if bashio::var.is_empty "${label}"; then
    label="HA Supervisor"
fi

api_key=$(bashio::config 'nyxid_api_key')
if bashio::var.is_empty "${api_key}"; then
    bashio::log.fatal "NyxID API key is required."
    exit 1
fi

server_url=$(bashio::config 'nyxid_server_url')
api_base=$(echo "${server_url}" | sed 's|^wss://|https://|;s|^ws://|http://|;s|/api/v1/nodes/ws$||')

if [ ! -f "${NYXID_CONFIG}/config.toml" ]; then
    bashio::log.fatal "Node not registered — setup.sh should have run first."
    exit 1
fi
node_id=$(grep '^id' "${NYXID_CONFIG}/config.toml" | head -1 | sed 's/.*= *"\(.*\)"/\1/')

# --------------------------------------------------------------------------
# Legacy migration: old add-ons stored the slug; new ones store the UUID.
# If we have the old file but not the new one, resolve slug → UUID once.
# --------------------------------------------------------------------------
if [ ! -f "${STATE_FILE}" ] && [ -f "${LEGACY_SLUG_FILE}" ]; then
    legacy_slug=$(cat "${LEGACY_SLUG_FILE}")
    bashio::log.info "Migrating legacy slug '${legacy_slug}' to UUID-anchored state..."
    legacy_id=$(curl -sf -H "Authorization: Bearer ${api_key}" \
        "${api_base}/api/v1/keys" \
        | jq -r --arg s "${legacy_slug}" '.keys[] | select(.slug == $s) | .id' \
        | head -1)
    if [ -n "${legacy_id}" ]; then
        echo "${legacy_id}" > "${STATE_FILE}"
        bashio::log.info "  Migrated to service id ${legacy_id}"
    fi
    rm -f "${LEGACY_SLUG_FILE}"
fi

# --------------------------------------------------------------------------
# Try to reuse a previously-provisioned service
# --------------------------------------------------------------------------
service_id=""
slug=""
if [ -f "${STATE_FILE}" ]; then
    saved_id=$(cat "${STATE_FILE}")
    resp=$(curl -sf -H "Authorization: Bearer ${api_key}" \
        "${api_base}/api/v1/keys/${saved_id}" 2>/dev/null || echo "")
    if [ -n "${resp}" ]; then
        current_node=$(echo "${resp}" | jq -r '.node_id // empty')
        current_label=$(echo "${resp}" | jq -r '.label // empty')
        current_slug=$(echo "${resp}" | jq -r '.slug // empty')
        current_ctype=$(echo "${resp}" | jq -r '.credential_type // empty')
        if [ "${current_node}" = "${node_id}" ] && [ "${current_ctype}" = "node_managed" ]; then
            service_id="${saved_id}"
            slug="${current_slug}"
            bashio::log.info "Reusing existing Supervisor service: ${slug} (id ${service_id})"
            # Sync label if user changed it in add-on config
            if [ "${current_label}" != "${label}" ]; then
                bashio::log.info "  Label changed: '${current_label}' → '${label}'"
                curl -sf -X PUT -H "Authorization: Bearer ${api_key}" \
                    -H "Content-Type: application/json" \
                    -d "{\"label\": \"${label}\"}" \
                    "${api_base}/api/v1/keys/${service_id}" >/dev/null || true
            fi
        else
            bashio::log.warning "Saved service mismatch (node or credential_type) — recreating."
            rm -f "${STATE_FILE}"
        fi
    else
        bashio::log.warning "Saved service id not found on server — recreating."
        rm -f "${STATE_FILE}"
    fi
fi

# --------------------------------------------------------------------------
# Create fresh service if needed.
# CRITICAL: auth_method + node_id MUST be in the initial POST.
# POST-then-PUT leaves the service stuck in credential_type=none (NyxID #419).
# --------------------------------------------------------------------------
if [ -z "${service_id}" ]; then
    bashio::log.info "Creating Supervisor service '${label}'..."
    create_resp=$(curl -sf -X POST \
        -H "Authorization: Bearer ${api_key}" \
        -H "Content-Type: application/json" \
        -d "{
            \"label\": \"${label}\",
            \"key_type\": \"http\",
            \"endpoint_url\": \"http://supervisor\",
            \"auth_method\": \"bearer\",
            \"auth_key_name\": \"Authorization\",
            \"node_id\": \"${node_id}\"
        }" \
        "${api_base}/api/v1/keys")
    if [ -z "${create_resp}" ]; then
        bashio::log.fatal "Failed to create Supervisor service (empty response)."
        exit 1
    fi
    service_id=$(echo "${create_resp}" | jq -r '.id // empty')
    slug=$(echo "${create_resp}" | jq -r '.slug // empty')
    if [ -z "${service_id}" ] || [ -z "${slug}" ]; then
        bashio::log.fatal "Service creation response missing id or slug: ${create_resp}"
        exit 1
    fi
    echo "${service_id}" > "${STATE_FILE}"
    bashio::log.info "  Created: ${slug} (id ${service_id})"
fi

# --------------------------------------------------------------------------
# Push credential on this node (every start — SUPERVISOR_TOKEN rotates)
# --------------------------------------------------------------------------
bashio::log.info "Pushing SUPERVISOR_TOKEN credential for ${slug}..."
nyxid node credentials --config "${NYXID_CONFIG}" add \
    --service "${slug}" \
    --header "Authorization" \
    --secret-format bearer \
    --value "${SUPERVISOR_TOKEN}" \
    --url "http://supervisor"

bashio::log.warning "============================================"
bashio::log.warning "SUPERVISOR ADMIN PROXY ACTIVE"
bashio::log.warning "  Service slug: ${slug}"
bashio::log.warning "  Call it with: nyxid proxy request ${slug} supervisor/info"
bashio::log.warning "  UNINSTALL this add-on when you're done."
bashio::log.warning "============================================"
