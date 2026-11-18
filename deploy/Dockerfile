# friday dash as a container on the master (built by `friday dash up` via deploy/compose.yaml).
#
# Build from the plugin root:  docker build -f deploy/Dockerfile .
#
# The dash's security rules are unchanged inside the container, because compose runs it with
# `network_mode: host` and mounts the host's tailscaled socket read-only:
#   - `tailscale ip -4` (through the socket) gives the host's tailnet IP, so the dash binds only
#     127.0.0.1 and that address, never 0.0.0.0 (resolve_binds refuses anything else);
#   - with the host network stack the dash sees real peer addresses, so `tailscale whois` still
#     maps each report's sender to the registry node it claims to be.
# The image carries no registry, token or state: nodes.toml is mounted read-only, GH_TOKEN comes
# from the environment, and the state dir is a volume.
FROM python:3.12-slim

# Pinned releases of the CLIs the dash shells out to (bump deliberately).
ARG TAILSCALE_VERSION=1.104.7
ARG GH_VERSION=2.105.0

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl; \
    . /etc/os-release; \
    install -d -m 0755 /usr/share/keyrings /etc/apt/sources.list.d; \
    curl -fsSL "https://pkgs.tailscale.com/stable/debian/${VERSION_CODENAME}.noarmor.gpg" \
        -o /usr/share/keyrings/tailscale-archive-keyring.gpg; \
    curl -fsSL "https://pkgs.tailscale.com/stable/debian/${VERSION_CODENAME}.tailscale-keyring.list" \
        -o /etc/apt/sources.list.d/tailscale.list; \
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg; \
    chmod 0644 /usr/share/keyrings/tailscale-archive-keyring.gpg /usr/share/keyrings/githubcli-archive-keyring.gpg; \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends "tailscale=${TAILSCALE_VERSION}" "gh=${GH_VERSION}"; \
    apt-get purge -y --auto-remove curl; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists

# Non-root runtime user; its config and state dirs exist so the read-only registry mount and the
# state volume land with the right owner.
RUN set -eux; \
    useradd --create-home --uid 1000 --user-group --shell /usr/sbin/nologin friday; \
    install -d -o friday -g friday /home/friday/.config /home/friday/.config/friday \
        /home/friday/.local /home/friday/.local/state /home/friday/.local/state/friday \
        /home/friday/.local/state/friday/dash

COPY bin/ /opt/friday/bin/
COPY lib/ /opt/friday/lib/
COPY dash/ /opt/friday/dash/

ENV PATH=/opt/friday/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/friday

USER friday
WORKDIR /home/friday
EXPOSE 8787

# --no-self: the dash only receives reports; the master pushes its own snapshot with its timer.
CMD ["friday", "dash", "--no-self"]
