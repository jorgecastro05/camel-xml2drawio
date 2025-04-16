# XML to Draw IO Diagram

## Installing the script:

    pip install camel_xml2drawio-0.0.x-py3-none-any.whl

Where x belongs to release version

## Running the script

    xml2drawio --xml xml_context_file.xml

## Building the project (for developers)

### Install dependencies
    
    python3 -m pip install --upgrade build
    python -m build
    
build and install

    python -m build && pip install dist/camel_xml2drawio-0.0.1-py3-none-any.whl --force-reinstall

### Docker run 

A dockerfile is provided for creating the app container image, can be used with docker or podman.

Example with podman:

    podman build -t xml2drawio .

Example with docker

    docker build -t xml2drawio .

For run the app mount a volume where the xml is located and run the container in interactive mode:

    podman run --privileged -it -v /home/user/Downloads/:/app:ro xml2drawio:latest /bin/bash

    docker run -it -v /home/user/Downloads/:/app:ro xml2drawio:latest /bin/bash


Then run the utility

    xml2drawio --xml context.xml
