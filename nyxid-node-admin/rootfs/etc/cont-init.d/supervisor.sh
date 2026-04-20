#!/command/with-contenv bashio
# ==============================================================================
# NyxID Node (Admin) — Supervisor service binding
# Runs AFTER the inherited setup.sh (lexicographic order: setup.sh < supervisor.sh)
# ==============================================================================

NYXID_CONFIG="/data/nyxid-node"
LAST_SLUG_FILE="/data/last-supervisor-slug"

supervisor_slug=$(bashio::config 'supervisor_service_slug')

# Reclaim previously-bound slug if user changed it
prev_slug=""
[ -f "${LAST_SLUG_FILE}" ] && prev_slug=$(cat "${LAST_SLUG_FILE}")
if [ -n "${prev_slug}" ] && [ "${prev_slug}" != "${supervisor_slug}" ]; then
    bashio::log.info "Removing previous supervisor credential: ${prev_slug}"
    nyxid node credentials --config "${NYXID_CONFIG}" remove \
        --service "${prev_slug}" || true
    rm -f "${LAST_SLUG_FILE}"
fi

if bashio::var.is_empty "${supervisor_slug}"; then
    bashio::log.warning "============================================"
    bashio::log.warning "Supervisor Service Slug is not configured."
    bashio::log.warning ""
    bashio::log.warning "Run on your machine:"
    bashio::log.warning ""
    bashio::log.warning "  nyxid service add --custom \\"
    bashio::log.warning "    --label 'HA Supervisor' \\"
    bashio::log.warning "    --endpoint-url 'http://supervisor' \\"
    bashio::log.warning "    --auth-method none"
    bashio::log.warning ""
    bashio::log.warning "Then paste the slug into add-on config and restart."
    bashio::log.warning "============================================"
    exit 0
fi

if [ ! -f "${NYXID_CONFIG}/config.toml" ]; then
    bashio::log.fatal "Node not registered — setup.sh should have run first."
    exit 1
fi

node_id=$(grep '^id' "${NYXID_CONFIG}/config.toml" | head -1 | sed 's/.*= *"\(.*\)"/\1/')
server_url=$(bashio::config 'nyxid_server_url')
api_base=$(echo "${server_url}" | sed 's|^wss://|https://|;s|^ws://|http://|;s|/api/v1/nodes/ws$||')
api_key=$(bashio::config 'nyxid_api_key')

# Bind supervisor service to this admin node (idempotent)
if ! bashio::var.is_empty "${api_key}"; then
    nyxid service update "${supervisor_slug}" \
        --node-id "${node_id}" \
        --access-token "${api_key}" \
        --base-url "${api_base}" 2>/dev/null || true
fi

bashio::log.warning "============================================"
bashio::log.warning "SUPERVISOR ADMIN PROXY ACTIVE"
bashio::log.warning "  Service slug: ${supervisor_slug}"
bashio::log.warning "  This container has HA Supervisor admin access."
bashio::log.warning "  UNINSTALL this add-on when you're done."
bashio::log.warning "============================================"

bashio::log.info "Updating Supervisor credential (slug: ${supervisor_slug})..."
nyxid node credentials --config "${NYXID_CONFIG}" add \
    --service "${supervisor_slug}" \
    --header "Authorization" \
    --secret-format bearer \
    --value "${SUPERVISOR_TOKEN}" \
    --url "http://supervisor"

echo "${supervisor_slug}" > "${LAST_SLUG_FILE}"
