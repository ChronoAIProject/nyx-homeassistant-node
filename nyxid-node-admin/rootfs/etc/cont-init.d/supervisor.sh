#!/command/with-contenv bashio
# ==============================================================================
# NyxID Node (Admin) — push the SUPERVISOR_TOKEN to a pre-created Supervisor
# service, node-locally. Runs AFTER the inherited setup.sh.
#
# NyxID rejects ALL /api/v1/keys access via API keys (403 / error_code 1002 —
# create, list, AND get-by-id). So this add-on CANNOT create, look up, or
# verify the service itself. The operator creates it ONCE as a user, bound to
# THIS node (the node id is printed below on first run):
#
#   nyxid service add --custom --slug ha-supervisor --label 'HA Supervisor' \
#     --via-node <node id> --endpoint-url http://supervisor \
#     --auth-method bearer --auth-key-name Authorization --org <org-slug>
#   nyxid service update <service id> --node-id <node id>   # ensure it's bound
#
# ...and this script pushes the (rotating) SUPERVISOR_TOKEN to that slug on
# every start — a purely node-local operation that never touches /api/v1/keys.
# ==============================================================================

NYXID_CONFIG="/data/nyxid-node"

slug=$(bashio::config 'supervisor_service_slug')
if bashio::var.is_empty "${slug}" || [ "${slug}" = "null" ]; then
    slug="ha-supervisor"
fi

if [ ! -f "${NYXID_CONFIG}/config.toml" ]; then
    bashio::log.fatal "Node not registered — setup.sh should have run first."
    exit 1
fi
node_id=$(grep '^id' "${NYXID_CONFIG}/config.toml" | head -1 | sed 's/.*= *"\(.*\)"/\1/')

bashio::log.info "Pushing SUPERVISOR_TOKEN to service '${slug}' on node ${node_id} (node-local)..."
if nyxid node credentials --config "${NYXID_CONFIG}" add \
        --service "${slug}" \
        --header "Authorization" \
        --secret-format raw \
        --value "Bearer ${SUPERVISOR_TOKEN}" \
        --url "http://supervisor"; then
    bashio::log.warning "============================================"
    bashio::log.warning "SUPERVISOR ADMIN PROXY ACTIVE"
    bashio::log.warning "  Service slug: ${slug}"
    bashio::log.warning "  Call it with: nyxid proxy request ${slug} supervisor/info"
    bashio::log.warning "  UNINSTALL this add-on when you're done."
    bashio::log.warning "============================================"
else
    bashio::log.error "Could not push the credential to service '${slug}' (is it created + bound to THIS node?)."
    bashio::log.error "Create it ONCE as a user, bound to THIS node, then restart this add-on:"
    bashio::log.error "  nyxid service add --custom --slug ${slug} --label 'HA Supervisor' \\"
    bashio::log.error "    --via-node ${node_id} --endpoint-url http://supervisor \\"
    bashio::log.error "    --auth-method bearer --auth-key-name Authorization --org <org-slug>"
    bashio::log.error "  nyxid service update <service-id> --node-id ${node_id}"
    bashio::log.error "(API keys cannot create/list services — NyxID error_code 1002 — so this"
    bashio::log.error " add-on can only push the token to a service you pre-create.)"
fi
