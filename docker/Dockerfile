# ER execution environment — fat base image (LOGIC.md §3.3, option 1).
#
# Pre-installs the system libraries needed by the vast majority of CRAN
# packages so per-paper `renv::restore()` does not fail on a missing .so.
# This trades ~200 MB of image size for eliminating a whole class of
# reproduction failures.
#
# Tagged by R version: ghcr.io/sistm/ai4reproducibility:r<version>.
# Built only when this file changes (see .github/workflows/docker.yml).
#
# The R version is a build arg so one Dockerfile produces every tag:
#   docker build --build-arg R_VERSION=4.4.2 -t ghcr.io/sistm/ai4reproducibility:r4.4.2 docker/
ARG R_VERSION=4.4.2
FROM r-base:${R_VERSION}

# System libraries covering ~95% of CRAN packages. Grouped by what pulls them:
#   curl/ssl/xml  — httr, curl, xml2, openssl, the tidyverse data stack
#   fontconfig/harfbuzz/fribidi — systemfonts, textshaping, ragg (ggplot2 deps)
#   png/tiff/jpeg — raster image output, magick, figure rendering
#   cairo/xt      — Cairo graphics device (deterministic-ish plot backend)
#   gsl/gmp/mpfr  — common in statistics packages
RUN apt-get update && apt-get install -y --no-install-recommends \
        libcurl4-openssl-dev \
        libssl-dev \
        libxml2-dev \
        libfontconfig1-dev \
        libharfbuzz-dev \
        libfribidi-dev \
        libpng-dev \
        libtiff5-dev \
        libjpeg-dev \
        libcairo2-dev \
        libxt-dev \
        libgsl-dev \
        libgmp-dev \
        libmpfr-dev \
        libgit2-dev \
        pandoc \
    && rm -rf /var/lib/apt/lists/*

# renv is the only R package baked in; everything else comes from the
# submission's lockfile via renv::restore() at run time.
RUN R -e "install.packages('renv', repos='https://cloud.r-project.org')"

# The orchestrator mounts the submission here and runs as this directory.
WORKDIR /workspace

# No ENTRYPOINT: the ER orchestrator passes an explicit `Rscript ...` command
# to `docker run`, so the container stays a thin execution surface.
