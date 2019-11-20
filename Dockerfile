FROM frolvlad/alpine-python3

COPY src app/src
RUN apk add build-base automake libtool libffi-dev python3-dev linux-headers
RUN pip3 install -r app/src/requirements.txt

WORKDIR /app/src/

ENTRYPOINT ["python3", "main.py"]
