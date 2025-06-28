FROM ubuntu:latest
USER root

ENV GOOGLE_APPLICATION_CREDENTIALS=/app/config/adc.json
ENV CACHE_DB_PATH=/app/config

######################
## Install Packages ##
######################

RUN apt-get update
RUN apt-get -y install software-properties-common
RUN add-apt-repository ppa:deadsnakes/ppa && apt-get update
RUN apt-get -y install python3 && apt-get -y install python3-pip && apt-get -y install python3-poetry

##################
## Add Src Code ##
##################
ADD event_engine /app/event_engine
COPY pyproject.toml /app
COPY README.md /app


#########################################
## Making Users and Setting Permisions ##
#########################################
RUN groupadd eventg
RUN useradd -m -g eventg eventscraper
RUN chown eventscraper:eventg -R /app
RUN find /app/event_engine -type f -exec chmod u=r,g=r,o= {} +
RUN find /app/event_engine -type d -exec chmod u=rx,g=rx,o=rx {} +
RUN chmod u=rx,g=rx,o=rx /app/event_engine


#################################
## Install Python Dependencies ##
#################################

USER eventscraper
WORKDIR /app
RUN poetry install

RUN mkdir /app/config
VOLUME /app/config


######################################
## Copy Entrypoint and Install GoSu ##
######################################

USER root
ADD ./docker/entrypoint.sh /app/entrypoint.sh
RUN chmod u=rx,g=r,o=r /app/entrypoint.sh
RUN set -eux; \
	apt-get update; \
	apt-get install -y gosu; \
	rm -rf /var/lib/apt/lists/*; \
# verify that the binary works
	gosu nobody true
ENTRYPOINT ["/app/entrypoint.sh"]

