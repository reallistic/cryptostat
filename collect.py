import aiohttp
import asyncio
import logging
import ujson

from bitty import loggers
from bitty.consumers.gdax import GdaxConsumer
from bitty.consumers.poloniex import PoloniexConsumer

if __name__ == '__main__':
    logger = logging.getLogger('bitty')
else:
    logger = logging.getLogger(__name__)

json_dumps = ujson.dumps  # pylint: disable=no-member


PRODUCT_PAIRS = (
    ['BTC-USD'],
    ['ETH-USD'],
    ['ETH-BTC'],
    ['LTC-USD'],
    ['LTC-BTC']
)

DATA_URL = os.getenv('DATA_URL', 'http://localhost:9200/bitty-%s/trade/')

async def push_data(trade):
    data = trade.to_json()
    date = data['time'][:7]
    async with aiohttp.ClientSession() as session:
        async with session.post(DATA_URL % date,
                                data=json_dumps(data)) as resp:
            if resp.status < 200 or resp.status >= 300:
                logger.error('got bad status code while sending data %s',
                             resp.status)
        resp_text = await resp.text()


def collect(loop=None):
    if loop is None:
        loop = asyncio.get_event_loop()

    threads = []

    for product_ids in PRODUCT_PAIRS:
        logger.info('creating thread for pair: %s', product_ids)
        keeper = GdaxConsumer(product_ids, loop=loop)
        keeper.on_trade(push_data)
        keeper.spawn_consumer()
        threads.append(keeper)

    """
    keeper = PoloniexConsumer(['USDT_BTC'], loop=loop)
    keeper.on_trade(push_data)
    keeper.spawn_consumer()
    threads.append(keeper)
    """

    return threads


def main():
    loggers.setup()
    loop = asyncio.get_event_loop()
    threads = collect(loop=loop)
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info('exiting')
        cos = []
        for thread in threads:
            cos.append(thread.kill())

        loop.run_until_complete(asyncio.gather(*cos, loop=loop))
        loop.stop()


if __name__ == '__main__':
    main()
