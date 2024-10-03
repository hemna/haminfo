FROM python:3.11-slim

# Dockerfile for building a container during aprsd development.
ARG BRANCH
ARG UID
ARG GID

ENV CONTAINER_USER=haminfo
ENV APP_NAME=haminfo
ENV HOME=/home/haminfo
ENV APP_GIT=https://github.com/hemna/haminfo.git
ENV APP_BRANCH=${BRANCH:-master}
ENV VIRTUAL_ENV=$HOME/.venv3
ENV UID=${UID:-1000}
ENV GID=${GID:-1000}

ENV INSTALL=$HOME/install
RUN apt update
RUN apt install -y git build-essential cron sudo
RUN apt install -y libffi-dev python3-dev libssl-dev libpq-dev
RUN apt install -y libmemcached-dev zlib1g-dev
#RUN apt-get install -y apt-utils
#RUN apt-get install -y pkg-config
#RUN apt upgrade -y
#RUN apk add --update git wget bash
#RUN apk add --update gcc linux-headers musl-dev libffi-dev libc-dev
#RUN apk add --update openssl-dev
#RUN add cmd:pip3 lsb-release

RUN addgroup --gid $GID $CONTAINER_USER
RUN useradd -m -u $UID -g $CONTAINER_USER $CONTAINER_USER
RUN echo "haminfo  ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/haminfo
RUN usermod -aG sudo haminfo

ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

USER $CONTAINER_USER
RUN pip3 install --user wheel
#RUN python3 -m venv $VIRTUAL_ENV
#ENV PATH="$VIRTUAL_ENV/bin:$PATH"
#RUN echo "export PATH=\$PATH:\$HOME/.local/bin" >> $HOME/.bashrc
RUN echo "export PATH=${PATH}:$(python3 -c 'import site; print(site.USER_BASE)')/bin" >> $HOME/.bashrc
#RUN cat $HOME/.bashrc; sleep 10

USER root
RUN ln -s $HOME/.config/haminfo /config
RUN chown -R $CONTAINER_USER:$CONTAINER_USER /config

USER $CONTAINER_USER
WORKDIR $HOME
RUN mkdir $INSTALL
RUN git clone -b $APP_BRANCH $APP_GIT $INSTALL/haminfo
#USER root
RUN cd $INSTALL/haminfo && pip3 install --user .
RUN pip3 install --user gunicorn

#user $CONTAINER_USER
RUN mkdir -p $HOME/.config/haminfo
RUN $HOME/.local/bin/oslo-config-generator --namespace haminfo --namespace haminfo.db --namespace haminfo.flask --namespace oslo.log > /config/haminfo.conf

# override this to run another configuration
ENV CONF default
USER $CONTAINER_USER
VOLUME ["/config"]
EXPOSE 8081/tcp
EXPOSE 8081/udp

ADD bin/api_entry.sh $HOME/
ADD bin/reload_db.sh $HOME/
ADD bin/db_upgrade.sh $HOME/
ADD bin/cron_entry.sh $HOME/
ADD bin/run_mqtt.sh $HOME/
ENTRYPOINT ["/home/haminfo/api_entry.sh"]
