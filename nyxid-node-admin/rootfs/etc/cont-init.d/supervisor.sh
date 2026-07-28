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
# Fallback reuse: find an existing node-managed service already bound to THIS
# node (endpoint http://supervisor) — e.g. one a *user* pre-created because
# NyxID rejects service creation via API keys (403 / error_code 1002). Lets the
# add-on adopt it automatically, with no /data STATE_FILE seed required.
# --------------------------------------------------------------------------
if [ -z "${service_id}" ]; then
    listed=$(curl -sf -H "Authorization: Bearer ${api_key}" "${api_base}/api/v1/keys" 2>/dev/null || echo "")
    if [ -n "${listed}" ]; then
        match=$(echo "${listed}" | jq -r --arg n "${node_id}" \
            '[((.keys // .)[]? | select(.node_id == $n and .credential_type == "node_managed" and ((.endpoint_url // "") | test("supervisor"))))][0] // {} | "\(.id // "")\t\(.slug // "")"')
        found_id=$(printf '%s' "${match}" | cut -f1)
        found_slug=$(printf '%s' "${match}" | cut -f2)
        if [ -n "${found_id}" ] && [ "${found_id}" != "null" ]; then
            service_id="${found_id}"
            slug="${found_slug}"
            echo "${service_id}" > "${STATE_FILE}"
            bashio::log.info "Reusing existing Supervisor service found on this node: ${slug} (id ${service_id})"
        fi
    fi
fi

# --------------------------------------------------------------------------
# Create fresh service if needed.
# CRITICAL: auth_method + node_id MUST be in the initial POST.
# POST-then-PUT leaves the service stuck in credential_type=none (NyxID #419).
# --------------------------------------------------------------------------
if [ -z "${service_id}" ]; then
    bashio::log.info "Creating Supervisor service '${label}'..."
    # NOTE: no `curl -sf` here — a 4xx used to make the script die with
    # `exited 22` and no diagnostics. Capture status + body and surface it.
    create_raw=$(curl -s -w $'\n%{http_code}' -X POST \
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
    create_code=$(printf '%s' "${create_raw}" | tail -n1)
    create_body=$(printf '%s' "${create_raw}" | sed '$d')
    if [ "${create_code}" = "200" ] || [ "${create_code}" = "201" ]; then
        service_id=$(echo "${create_body}" | jq -r '.id // empty')
        slug=$(echo "${create_body}" | jq -r '.slug // empty')
        if [ -n "${service_id}" ] && [ -n "${slug}" ]; then
            echo "${service_id}" > "${STATE_FILE}"
            bashio::log.info "  Created: ${slug} (id ${service_id})"
        fi
    else
        bashio::log.error "Could not create the Supervisor service (HTTP ${create_code}): ${create_body}"
        if [ "${create_code}" = "403" ]; then
            bashio::log.error "NyxID rejects service creation via API keys (error_code 1002)."
        fi
        bashio::log.error "Create it ONCE as a user, then restart this add-on (it will adopt it):"
        bashio::log.error "  nyxid service add --custom --slug ha-supervisor --label '${label}' \\"
        bashio::log.error "    --via-node ${node_id} --endpoint-url http://supervisor --auth-method bearer"
        bashio::log.error "  (append --org <org-slug> to make it organisation-scoped)"
    fi
fi

# --------------------------------------------------------------------------
# Push credential on this node (every start — SUPERVISOR_TOKEN rotates).
# Only when a service is actually bound, so a failed provision doesn't crash.
# --------------------------------------------------------------------------
if [ -n "${service_id}" ] && [ -n "${slug}" ]; then
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
else
    bashio::log.warning "No Supervisor service bound to this node yet — credential not pushed."
    bashio::log.warning "Follow the 'nyxid service add' instructions above, then restart this add-on."
fi
