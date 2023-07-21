import asyncio

from guacamole.client import BUF_LEN, BaseGuacamoleClient
from guacamole.instruction import GuacamoleInstruction as Instruction


class AsyncGuacamoleClient(BaseGuacamoleClient):
    """Asynchronous Guacamole Client class."""

    def __init__(self, host, port, timeout=20, debug=False, logger=None):
        """
        Asynchronous Guacamole Client class. This class can handle communication with
        guacd server.

        :param host: guacd server host.

        :param port: guacd server port.

        :param timeout: socket connection timeout.

        :param debug: if True, default logger will switch to Debug level.
        """
        self._stream_reader = None
        self._stream_writer = None
        super(AsyncGuacamoleClient, self).__init__(host, port, timeout, debug, logger)

    async def _connect(self):
        self._stream_reader, self._stream_writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), timeout=self.timeout
        )
        self.logger.info('Client connected with guacd server (%s, %s, %s)'
                         % (self.host, self.port, self.timeout))

    async def _get_stream_reader(self):
        if not self._stream_reader:
            await self._connect()
        return self._stream_reader

    async def _get_stream_writer(self):
        if not self._stream_reader:
            await self._connect()
        return self._stream_writer

    async def close(self):
        writer = await self._get_stream_writer()
        writer.close()
        await writer.wait_closed()
        self._stream_writer = self._stream_reader = None
        super(AsyncGuacamoleClient, self).close()

    async def receive(self):
        reader = await self._get_stream_reader()
        instruction_generator = self._decode_instruction()
        instruction = next(instruction_generator, None)

        while not instruction:
            try:
                instruction = instruction_generator.send(await reader.read(BUF_LEN))
            except StopIteration:
                await self.close()
                return None
        return instruction

    async def send(self, data):
        super(AsyncGuacamoleClient, self).send(data)
        writer = await self._get_stream_writer()
        writer.write(data)
        await writer.drain()

    async def read_instruction(self):
        """
        Read and decode instruction.
        """
        super(AsyncGuacamoleClient, self).read_instruction()
        return Instruction.load(await self.receive())

    async def send_instruction(self, instruction):
        """
        Send instruction after encoding.
        """
        super(AsyncGuacamoleClient, self).send_instruction(instruction)
        return await self.send(instruction.encode().encode("utf8"))

    async def handshake(self, protocol='vnc', width=1024, height=768, dpi=96,
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
                    await self.close()
                    return
                for instruction in instructions:
                    await self.send_instruction(instruction)
                response = await self.read_instruction()
                instructions = handshake_generator.send(response)
            except StopIteration:
                break

