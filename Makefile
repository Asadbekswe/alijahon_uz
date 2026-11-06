COMPOSE ?= docker compose
RUN = $(COMPOSE) exec web

.PHONY: env up down build logs ps migrate makemigrations seed test lint shell createsuperuser compile makemessage

env:            ## create .env with random development secrets
	python3 scripts/make_dev_env.py

build:
	$(COMPOSE) build

up:             ## start the dev stack (web, MySQL, Redis)
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100 web

ps:
	$(COMPOSE) ps

migrate:
	$(RUN) python manage.py migrate

makemigrations:
	$(RUN) python manage.py makemigrations apps

seed:           ## idempotent development data
	$(RUN) python manage.py seed_dev_data

test:
	$(RUN) pytest -q

lint:
	$(RUN) flake8 apps root

shell:
	$(RUN) python manage.py shell

createsuperuser:
	$(RUN) python manage.py createsuperuser

compile:
	$(RUN) python manage.py compilemessages --locale=uz --locale=ru --locale=oz

makemessage:
	$(RUN) python manage.py makemessages -l ru -l uz -l oz
