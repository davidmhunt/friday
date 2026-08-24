# syntax=docker/dockerfile:1
FROM ubuntu:24.04

# Ubuntu LTS (not a slim Debian image) so this base doubles as a ROS-ready
# environment for future robotics projects without a base-image migration.

ARG USER_UID=1000
ARG USER_GID=1000
ARG INSTALL_LATEX=true
ARG NODE_MAJOR=20

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        openssh-client \
        curl \
        ca-certificates \
        build-essential \
        gnupg \
    && rm -rf /var/lib/apt/lists/*

# LaTeX toolchain (optional — costs several GB, gate it off for a lean
# code-only container via --build-arg INSTALL_LATEX=false)
RUN if [ "$INSTALL_LATEX" = "true" ]; then \
        apt-get update && apt-get install -y --no-install-recommends \
            texlive-latex-extra \
            texlive-fonts-recommended \
            texlive-latex-recommended \
            latexmk \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# Node.js (for the Claude Code CLI) via NodeSource — Ubuntu's bundled
# nodejs is usually too old for current CLI requirements.
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @anthropic-ai/claude-code

# uv, via the official installer (matches this project's own quickstart)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:/home/agent/.local/bin:${PATH}"

# Non-root user, UID/GID matched to the host so bind-mounted files aren't
# owned by a mismatched UID.
RUN groupadd -g ${USER_GID} agent \
    && useradd -m -u ${USER_UID} -g ${USER_GID} -s /bin/bash agent

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER agent
WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["bash"]
