FROM python:3.12


ENV PYTHONUNBUFFERED=1

# create root directory for our project in the container
# RUN mkdir /TellMe

WORKDIR /app


# Install dependencies
COPY requirements.txt /app/
RUN pip install -r requirements.txt

# Copy the project code into the container
COPY . /app/