FROM ghcr.io/open-webui/open-webui:main

# Fixed versions for the Critical findings identified by the staged Trivy gate.
RUN python -m pip install --no-cache-dir --upgrade --upgrade-strategy eager \
    "nltk==3.10.3" \
    "unstructured==0.24.0"
