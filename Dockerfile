FROM jackton1/alpine-python3-numpy-pandas

COPY . app
RUN pip3 install -r app/requirements.txt

WORKDIR /app/src/

ENV CLIENT_ID=$CLIENT_ID
ENV CLIENT_SECRET=$CLIENT_SECRET
ENV USERNAME=$USERNAME
ENV PASSWORD=$PASSWORD

ENTRYPOINT ["python3", "main.py"]
