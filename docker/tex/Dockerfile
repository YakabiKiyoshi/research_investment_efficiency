FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=ja_JP.UTF-8
ENV LANGUAGE=ja_JP:ja
ENV LC_ALL=ja_JP.UTF-8

WORKDIR /workspace

RUN apt-get update && apt-get install -y \
    locales \
    ca-certificates \
    git \
    curl \
    wget \
    make \
    vim \
    less \
    nodejs \
    npm \
    latexmk \
    biber \
    chktex \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-luatex \
    texlive-lang-japanese \
    texlive-fonts-recommended \
    fonts-noto-cjk \
    fonts-noto-cjk-extra \
    && sed -i '/ja_JP.UTF-8/s/^# //g' /etc/locale.gen \
    && sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen \
    && locale-gen \
    && update-locale LANG=ja_JP.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

CMD ["bash"]