# Security

This repository processes untrusted PDF uploads and should not be exposed directly to the public Internet without additional controls.

Before production deployment:

- place both APIs behind TLS and authentication;
- enforce upload size and request-rate limits at the reverse proxy;
- isolate containers and restrict outbound network access where possible;
- scan uploaded files according to your organization’s policy;
- keep GROBID admin and internal service ports private;
- use a non-root runtime and read-only container filesystem where practical;
- store secrets outside Git and rotate them regularly;
- apply retention policies to original PDFs and generated assets;
- review licenses and data-handling requirements for PDFs and models;
- monitor dependency and container-image vulnerabilities.

Report security issues privately to the repository owner rather than opening a public issue.
