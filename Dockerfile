# Dockerfile
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    curl \
    bash \
    git \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# opencode 설치
RUN curl -fsSL https://opencode.ai/install | bash

# PATH 설정
ENV PATH="/root/.opencode/bin:${PATH}"

WORKDIR /workspace

CMD ["/bin/bash"]
