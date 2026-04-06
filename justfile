# auction-monitor — local dev recipes
# Usage: just <recipe>
# Run from ~/development/nellis_auction_monitor/

cluster       := env("CLUSTER", "kind")
registry_port := env("REGISTRY_PORT", "5001")
namespace     := "auction-monitor"

# Show available recipes
default:
    @just --list

# Build, push to local registry, and apply all manifests
deploy:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! docker ps --filter "name=kind-registry" --format "{{{{.Names}}" | grep -q "kind-registry"; then
        echo "✗ Local registry is not running. Run 'just start' from the kubernetes directory." >&2; exit 1
    fi
    echo "=> Building auction-monitor image..."
    docker build -t localhost:{{registry_port}}/auction-monitor:dev .
    echo "=> Pushing to local registry..."
    docker push localhost:{{registry_port}}/auction-monitor:dev
    echo "=> Applying manifests..."
    kubectl apply -f k8s/ --context "kind-{{cluster}}"
    echo "✓ auction-monitor deployed."
    echo "  Check status: kubectl get pods -n {{namespace}}"

# Create/update the Secret from .env
secret:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -f ".env" ]; then
        echo "✗ .env not found. Copy .env.example and fill in your values." >&2; exit 1
    fi
    kubectl create namespace "{{namespace}}" --context "kind-{{cluster}}" 2>/dev/null || true
    kubectl create secret generic auction-monitor-env \
        -n "{{namespace}}" \
        --context "kind-{{cluster}}" \
        --from-env-file=.env \
        --dry-run=client -o yaml | kubectl apply -f -
    echo "✓ auction-monitor secret created/updated."

# Stream logs from the auction-monitor pod
logs:
    kubectl logs -n "{{namespace}}" --context "kind-{{cluster}}" \
        --all-containers --prefix --follow \
        -l app=auction-monitor

# Restart the auction-monitor pod (triggers a fresh pull of the current image)
restart:
    kubectl rollout restart deployment/auction-monitor \
        -n "{{namespace}}" --context "kind-{{cluster}}"
    kubectl rollout status deployment/auction-monitor \
        -n "{{namespace}}" --context "kind-{{cluster}}"
    echo "✓ auction-monitor restarted."

# Remove all auction-monitor resources from the cluster
teardown:
    kubectl delete -f k8s/ --context "kind-{{cluster}}" --ignore-not-found
    echo "✓ auction-monitor removed from cluster."
