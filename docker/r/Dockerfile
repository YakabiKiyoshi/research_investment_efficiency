FROM rocker/r-ver:4.4.2

WORKDIR /workspace

ENV RENV_PATHS_LIBRARY=/workspace/renv/library

RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    build-essential \
    ca-certificates \
    vim \
    less \
    nodejs \
    npm \
    libcurl4-openssl-dev \
    libssl-dev \
    libxml2-dev \
    libfontconfig1-dev \
    libharfbuzz-dev \
    libfribidi-dev \
    libfreetype6-dev \
    libpng-dev \
    libtiff5-dev \
    libjpeg-dev \
    libgit2-dev \
    && rm -rf /var/lib/apt/lists/*

RUN R -e "install.packages(c('renv', 'languageserver', 'IRkernel'), repos='https://cloud.r-project.org')"

CMD ["bash"]