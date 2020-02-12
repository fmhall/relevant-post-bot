FROM jackton1/alpine-python3-numpy-pandas

COPY src app/src
RUN pip3 install -r app/src/requirements.txt

WORKDIR /app/src/

ENTRYPOINT ["python3", "main.py"]
