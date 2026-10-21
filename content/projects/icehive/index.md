---
title: IceHive
ai_usage: "Level 1: Assistant"
types: "Infrastructure & DevOps"
technologies: [Go]
repo: jamesread/icehive
logo: https://raw.githubusercontent.com/jamesread/icehive/main/logo.svg
tags: [Golang, ConnectRPC, RabbitMQ]
maturity: Alpha
involvement: Founder
screenshots:
  - file: "screenshots/home.png"
    title: "Home and live activity"
    description: "The home page links to every area of IceHive and streams a live feed of heartbeats, collection requests and runs, so you can see data flowing without opening logs or a broker console."
  - file: "screenshots/sources.png"
    title: "Collection sources"
    description: "Every source being collected (GitHub repos and orgs, RSS feeds, mailboxes) in one table, with its schedule in plain English, last success and a health badge, so broken or overdue sources stand out and can be run on demand."
  - file: "screenshots/source-details.png"
    title: "Source details"
    description: "Everything about a single source on one page (spec, schedule, last run, last success, pipeline status and last error), the place to start when data has not updated."
  - file: "screenshots/source-create.png"
    title: "Adding a source"
    description: "Add something new to collect from the UI by picking a collector type, writing a source spec and setting a schedule, with no config change or redeploy."
  - file: "screenshots/services.png"
    title: "Service heartbeats"
    description: "Which collectors, persisters and controllers are running, the version each reports and when it last checked in, confirming a deployment came up and catching stopped workers."
  - file: "screenshots/config.png"
    title: "Controller configuration"
    description: "Shared settings such as message broker and database connections, edited in the UI and handed out to workers, with passwords and tokens always redacted."
  - file: "screenshots/home-dark.png"
    title: "Dark mode"
    description: "The home page in the built-in dark theme, for operators who prefer dark dashboards."
annotations:
  Started: "2026"
description: |
  Microservices that collect data from various APIs, normalize it, and store it in a database.
---
