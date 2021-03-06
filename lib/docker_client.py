#! /usr/bin/env python
# -*- coding: utf-8 -*-
# vim:fenc=utf-8
#
# Copyright © 2013 xavier <xavier@laptop-300E5A>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


#From https://github.com/dotcloud/docker-py
#TODO Automate:  sudo docker -H 192.168.0.17:4242 -H 127.0.0.1:4243 -d &
#TODO Automate:  sudo docker -H 0.0.0.0:4243 -d &
#NOTE No way to get output ? If start fails for example


import requests
import docker
import json
#TODO Default without output, arg to turn it on
#TODO Attach command to test with a running container
from clint.textui import puts, indent, colored
from pprint import pprint
import os


SSH_PORT = 22


class Image(object):

    def __init__(self, client, name, tag=None):
        self._client = client
        self.id = self._get_id(base=name, tag=tag)
        self.tag = tag
        self.history = json.loads(self._client.history(self.id))
        self.properties = self._client.inspect_image(self.id)

    def inspect(self):
        #NOTE Not really cool, but http has cool prints
        os.system(
            'http {}:{}/images/{}/json'.format(
                os.environ['SERVERDEV_IP'],
                os.environ['SERVERDEV_PORT'],
                self.id))

    def _get_id(self, base, tag=None):
        #TODO Dates stuff, for now return the latest
        candidates = self._get_list_images(name=base)

        if tag and candidates:
            candidates = filter(lambda image: tag == image['Tag'], candidates)

        if not candidates:
            raise ValueError('No image found')

        return sorted(
            candidates, key=lambda image: image['Created'])[-1]['Id']

    def _get_list_images(self, **kwargs):
        #TODO Add description (inspect image as a 'comment' section
        all_images = self._client.images(**kwargs)
        # We don't need image without description
        return filter(lambda image: 'Repository' in image, all_images)

    def remove(self):
        self._client.remove_image(self.id)

    def tag(self, repository, **kwargs):
        tag = kwargs.get('tag', self.tag)
        self._client.tag(
            self.id, repository, tag=tag, force=kwargs.get('force', False))


class Container(object):

    def __init__(self, client, name, is_running=False):
        #TODO A cool way to display self.properties
        self._client = client
        self.running = is_running
        self.id = self._get_id(name)
        self.properties = self._client.inspect_container(self.id)

    def inspect(self):
        #NOTE Not really cool
        os.system(
            'http {}:{}/containers/{}/json'.format(
                os.environ['SERVERDEV_IP'],
                os.environ['SERVERDEV_PORT'],
                self.id))

    def _get_id(self, name):
        #TODO Dates stuff, for now return the latest
        containers = self._client.containers(all=(not self.running))
        candidates = filter(lambda box: box['Image'] == name, containers)

        if not candidates:
            raise ValueError('No container found')

        return sorted(candidates, key=lambda box: box['Created'])[-1]['Id']

    def logs(self, display=False):
        logs = self._client.logs(self.id).encode('utf-8')
        if display:
            puts(colored.green('Got container logs:'))
            with indent(4, '..'):
                puts(colored.blue(logs))
        else:
            return logs

    def attach(self):
        puts(colored.green('Streaming logs, hit CTRL-C to stop'))
        stream = self._client.attach(self.id)
        with indent(4, quote='..'):
            try:
                while True:
                    puts(colored.blue(stream.next()))
            except KeyboardInterrupt:
                puts(colored.red('Streaming stopped'))
            #FIXME Should not happen
            except StopIteration:
                puts(colored.red('Could not fetch more logs'))

    def get_port_mapping(self, port):
        try:
            forwarded_port = self._client.port(self.id, port)
        except TypeError:
            return None
        #NOTE May be useless now
        if not forwarded_port:
            return None

        return self._client.port(self.id, port).encode('utf-8')

    def forwarded_ssh(self):
        return self.get_port_mapping(SSH_PORT)

    def stop(self, timeout=None):
        self._client.stop(self.id, timeout=timeout)

    def remove(self):
        self._client.remove_container(self.id)

    def kill(self):
        self._client.kill(self.id)

    def restart(self):
        #FIXME Restart nothing, change nothing
        self._client.restart(self.id)

    def start(self, attach=False, **kwargs):
        self._client.start(self.id, **kwargs)
        if attach:
            self.attach()

    def commit(self, **kwargs):
        self._client.commit(self.id, **kwargs)


class DockerClient(object):

    def __init__(self, host='localhost', port='4243', version='1.3'):
        #TODO Implement a test to check if it worked
        self._client = docker.Client(
            base_url='http://{}:{}'.format(host, port), version=version)
        try:
            self.properties = self._client.info()
            self.properties.update(self._client.version())
        except requests.exceptions.ConnectionError as e:
            puts(colored.red('** Error connection to server:\n\t{}'.format(
                e.message)))
            import sys
            sys.exit(1)

    def inspect(self):
        pprint(self.properties)

    def list_images(self, **kwargs):
        #TODO Add description (inspect image as a 'comment' section
        all_images = self._client.images(**kwargs)
        # We don't need image without description
        images_description = filter(
            lambda image: 'Repository' in image, all_images)

        puts(colored.green('[ .. ] {} images available out of {}'.format(
            len(images_description), len(all_images))))
        with indent(4, quote='-'):
            for image in images_description:
                puts(colored.blue('[{}] {} - {}'.format(
                    image['Id'][:12],
                    image['Repository'],
                    image['Tag'])))

    def list_containers(self, **kwargs):
        #TODO Description as well ?
        #TODO Filter with real image name ?
        all_containers = self._client.containers(**kwargs)

        puts(colored.green('[ .. ] {} containers'.format(
            len(all_containers))))
        for container in all_containers:
            with indent(4, quote='-'):
                puts(colored.blue('[{}][{}] {} - {}'.format(
                    container['Id'][:12],
                    container['Status'],
                    container['Image'],
                    container['Command'])))

    def build_container(self, image_name, command, tag=None, **kwargs):
        image_id = self.image(image_name, tag=tag).id
        self._client.create_container(image_id, command, **kwargs)

    def execute(self, image_name, command, tag='latest', **kwargs):
        image_id = self.image(image_name, tag=tag).id
        self._client.create_container(image_id, command, **kwargs)
        container = self.container(':'.join([image_name, tag]))
        container.start(attach=kwargs.get('attach', False))

    def container(self, name, is_running=False):
        return Container(self._client, name, is_running)

    def image(self, base, tag=None):
        return Image(self._client, base, tag=tag)

    def run(self, image, cmd, **kwargs):
        winner_id = None
        containers = self._client.containers(all=True)
        #NOTE What about quotes with /bin/bash -c "cmd"
        candidates = filter(lambda box:
            (box['Image'] == image)
            and (box['Command'] == cmd),
            #and (box['Command'].replace('/bin/bash -c ', '') == cmd),
            containers)

        if candidates:
            puts(colored.blue('[ .. ] Suitable containers exist...'))
            # Already running ?
            stopped_boxes = filter(lambda box: box['Status'].find('Exit') == 0, candidates)

            # If yes, nothing to do
            # If no, let's start the latest
            if stopped_boxes:
                puts(colored.blue('[ .. ] but are stopped, restarting the latest'))
                winner_id = sorted(
                    stopped_boxes, key=lambda box: box['Created'])[-1]['Id']
                self._client.start(winner_id)
            else:
                puts(colored.blue('[ .. ] and are running, nothing to do'))

        else:
            puts(colored.blue('[ .. ] Found nothing, creates it from image {}'.format(image)))
            #TODO Check if the image exists
            self._client.create_container(image, cmd, **kwargs)
            winner_id = sorted(
                self._client.containers(all=True),
                key=lambda box: box['Created'])[-1]['Id']
            puts(colored.blue('[ .. ] Starting container with {}'.format(cmd)))
            self._client.start(winner_id)

        if winner_id:
            return self.container(image)

        return None
