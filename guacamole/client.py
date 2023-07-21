"""
The MIT License (MIT)

Copyright (c)   2014 rescale
                2014 - 2016 Mohab Usama
"""
import abc
import socket
import logging

import six

from guacamole import logger as guac_logger

from guacamole.exceptions import GuacamoleError

from guacamole.instruction import INST_TERM
from guacamole.instruction import GuacamoleInstruction as Instruction

# supported protocols
PROTOCOLS = ('vnc', 'rdp', 'ssh')

PROTOCOL_NAME = 'guacamole'

BUF_LEN = 4096


@six.add_metaclass(abc.ABCMeta)
class BaseGuacamoleClient(object):
    """Guacamole Client class."""

    def __init__(self, host, port, timeout=20, debug=False, logger=None):
        """
        Guacamole Client class. This class can handle communication with guacd
        server.

        :param host: guacd server host.

        :param port: guacd server port.

        :param timeout: socket connection timeout.

        :param debug: if True, default logger will switch to Debug level.
        """
        self.host = host
        self.port = port
        self.timeout = timeout

        self._client = None

        # handshake established?
        self.connected = False

        # Receiving buffer
        self._buffer = bytearray()

        # Client ID
        self._id = None

        self.logger = guac_logger
        if logger:
            self.logger = logger

        if debug:
            self.logger.setLevel(logging.DEBUG)

    @property
    def id(self):
        """Return client id"""
        return self._id

    @abc.abstractmethod
    def close(self):
        self.connected = False
        self.logger.info('Connection closed.')

    @abc.abstractmethod
    def receive(self):
        pass

    def _decode_instruction(self):
        start = 0

        while True:
            idx = self._buffer.find(INST_TERM.encode(), start)
            if idx != -1:
                # instruction was fully received!
                line = self._buffer[:idx + 1].decode()
                self._buffer = self._buffer[idx + 1:]
                self.logger.debug('Received instruction: %s' % line)
                yield line
                return
            else:
                start = len(self._buffer)
                # we are still waiting for instruction termination
                buf = yield
                if not buf:
                    # No data recieved, connection lost?!
                    self.logger.warn(
                        'Failed to receive instruction. Closing.')
                    return
                self._buffer.extend(buf)

    @abc.abstractmethod
    def send(self, data):
        self.logger.debug('Sending data: %s' % data)

    @abc.abstractmethod
    def read_instruction(self):
        """
        Read and decode instruction.
        """
        self.logger.debug('Reading instruction.')

    @abc.abstractmethod
    def send_instruction(self, instruction):
        """
        Send instruction after encoding.
        """
        self.logger.debug('Sending instruction: %s' % str(instruction))

    def _handshake_generator(self, protocol='vnc', width=1024, height=768, dpi=96,
                  audio=None, video=None, image=None, width_override=None,
                  height_override=None, dpi_override=None, **kwargs):
        """
        Establish connection with Guacamole guacd server via handshake.

        """
        if protocol not in PROTOCOLS and 'connectionid' not in kwargs:
            self.logger.error(
                'Invalid protocol: %s and no connectionid provided' % protocol)
            raise GuacamoleError('Cannot start Handshake. '
                                 'Missing protocol or connectionid.')

        if audio is None:
            audio = list()

        if video is None:
            video = list()

        if image is None:
            image = list()

        # 1. Send 'select' instruction
        self.logger.debug('Send `select` instruction.')

        # if connectionid is provided - connect to existing connectionid
        if 'connectionid' in kwargs:
            next_instruction = Instruction('select', kwargs.get('connectionid'))
        else:
            next_instruction = Instruction('select', protocol)

        response_instruction = yield [next_instruction]

        # 2. Receive `args` instruction
        self.logger.debug('Expecting `args` instruction, received: %s'
                          % str(response_instruction))

        if not response_instruction:
            yield None
            raise GuacamoleError(
                'Cannot establish Handshake. Connection Lost!')

        if response_instruction.opcode != 'args':
            yield None
            raise GuacamoleError(
                'Cannot establish Handshake. Expected opcode `args`, '
                'received `%s` instead.' % response_instruction.opcode)

        # 3. Respond with size, audio & video support
        next_instructions = []
        self.logger.debug('Send `size` instruction (%s, %s, %s)'
                          % (width, height, dpi))
        next_instructions.append(Instruction('size', width, height, dpi))

        self.logger.debug('Send `audio` instruction (%s)' % audio)
        next_instructions.append(Instruction('audio', *audio))

        self.logger.debug('Send `video` instruction (%s)' % video)
        next_instructions.append(Instruction('video', *video))

        self.logger.debug('Send `image` instruction (%s)' % image)
        next_instructions.append(Instruction('image', *image))

        if width_override:
            kwargs["width"] = width_override
        if height_override:
            kwargs["height"] = height_override
        if dpi_override:
            kwargs["dpi"] = dpi_override

        # 4. Send `connect` instruction with proper values
        connection_args = [
            kwargs.get(arg.replace('-', '_'), '') for arg in response_instruction.args
        ]

        self.logger.debug('Send `connect` instruction (%s)' % connection_args)
        next_instructions.append(Instruction('connect', *connection_args))

        # 5. Receive ``ready`` instruction, with client ID.
        response_instruction = yield next_instructions
        self.logger.debug('Expecting `ready` instruction, received: %s'
                          % str(response_instruction))

        if response_instruction.opcode != 'ready':
            self.logger.warning(
                'Expected `ready` instruction, received: %s instead')

        if response_instruction.args:
            self._id = response_instruction.args[0]
            self.logger.debug(
                'Established connection with client id: %s' % self.id)

        self.logger.debug('Handshake completed.')
        self.connected = True

    @abc.abstractmethod
    def handshake(self, protocol='vnc', width=1024, height=768, dpi=96,
                                 audio=None, video=None, image=None,
                                 width_override=None,
                                 height_override=None, dpi_override=None, **kwargs):
        """
        Establish connection with Guacamole guacd server via handshake.

        """
        pass


class GuacamoleClient(BaseGuacamoleClient):
    """Guacamole Client class."""

    def __init__(self, host, port, timeout=20, debug=False, logger=None):
        """
        Guacamole Client class. This class can handle communication with guacd
        server.

        :param host: guacd server host.

        :param port: guacd server port.

        :param timeout: socket connection timeout.

        :param debug: if True, default logger will switch to Debug level.
        """
        self._client = None
        super(GuacamoleClient, self).__init__(host, port, timeout, debug, logger)

    @property
    def client(self):
        """
        Socket connection.
        """
        if not self._client:
            self._client = socket.create_connection(
                (self.host, self.port), self.timeout)
            self.logger.info('Client connected with guacd server (%s, %s, %s)'
                             % (self.host, self.port, self.timeout))

        return self._client

    def close(self):
        """
        Terminate connection with Guacamole guacd server.
        """
        self.client.close()
        self._client = None
        super(GuacamoleClient, self).close()

    def receive(self):
        """
        Receive instructions from Guacamole guacd server.
        """

        instruction_generator = self._decode_instruction()
        instruction = next(instruction_generator, None)

        while not instruction:
            try:
                instruction = instruction_generator.send(self.client.recv(BUF_LEN))
            except StopIteration:
                self.close()
                return None
        return instruction

    def send(self, data):
        """
        Send encoded instructions to Guacamole guacd server.
        """
        super(GuacamoleClient, self).send(data)
        self.client.sendall(data.encode())

    def read_instruction(self):
        """
        Read and decode instruction.
        """
        super(GuacamoleClient, self).read_instruction()
        return Instruction.load(self.receive())

    def send_instruction(self, instruction):
        """
        Send instruction after encoding.
        """
        super(GuacamoleClient, self).send_instruction(instruction)
        return self.send(instruction.encode())

    def handshake(self, protocol='vnc', width=1024, height=768, dpi=96,
                                 audio=None, video=None, image=None,
                                 width_override=None,
                                 height_override=None, dpi_override=None, **kwargs):
        handshake_generator = self._handshake_generator(
            protocol=protocol,
            width=width,
            height=height,
            dpi=dpi,
            audio=audio,
            video=video,
            image=image,
            width_override=width_override,
            height_override=height_override,
            dpi_override=dpi_override,
            **kwargs,
        )
        instructions = next(handshake_generator)
        while True:
            try:
                if instructions is None:
                    self.close()
                    return
                for instruction in instructions:
                    self.send_instruction(instruction)
                response = self.read_instruction()
                instructions = handshake_generator.send(response)
            except StopIteration:
                break
