import asyncio

from guacamole.client import BUF_LEN, BaseGuacamoleClient


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
        self._stream_reader, self._stream_writer = asyncio.open_connection(
            self.host, self.port, timeout=self.timeout
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
                return None
        return instruction

    async def send(self, data):
        super(AsyncGuacamoleClient, self).send(data)
        writer = await self._get_stream_writer()
        writer.write(data)
        await writer.drain()

