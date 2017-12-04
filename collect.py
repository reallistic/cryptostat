import os
import aiohttp
import asyncio
import logging
import ujson

import aiohttp.web

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

    icon = '📈' if trade.side == 'sell' else '📉'
    logger.debug('%s :: %s :: %s %s%s   %s %s', trade.exchange_name,
                 trade.product_id, trade.size,
                 trade.price, icon, trade.trade_id, trade.time)

    data = trade.to_json()
    date = data['time'][:7]
    async with aiohttp.ClientSession() as session:
        async with session.post(DATA_URL % date,
                                data=json_dumps(data)) as resp:
            if resp.status < 200 or resp.status >= 300:
                logger.error('got bad status code while sending data %s',
                             resp.status)
        resp_text = await resp.text()

def on_heartbeat(message):
    logger.debug('%s | %s :: heartbeat :: %s %s', message.exchange_name,
                 message.product_id, message.last_trade_id,
                 message.time)


CONSUMERS_AVAILABLE = dict(
    gdax=GdaxConsumer,
    poloniex=PoloniexConsumer
)

CONSUMER_PAIRS_ACTIVE = dict(
    gdax=[
        'BTC-USD',
        'ETH-USD',
        'ETH-BTC',
        'LTC-USD',
        'LTC-BTC'
    ],
    poloniex=[
        'USDT_REP',
        'USDT_BTC',
        'USDT_ETH'
    ]
)


def collect(app):
    loop = app.loop

    threads = []

    for consumer, pairs in CONSUMER_PAIRS_ACTIVE.items():
        for pair in pairs:
            logger.info('creating thread for %s pair: %s', consumer, pair)
            # legacy, I guess it makes most since to convert this
            # to 1-1
            product_ids = [pair]
            try:
                consumer_cls = CONSUMERS_AVAILABLE[consumer]
            except KeyError:
                logger.error('consumer %s not available', consumer)
                continue
            keeper = consumer_cls(product_ids, loop=loop)
            keeper.on_trade(push_data)
            keeper.on_heartbeat(on_heartbeat)
            keeper.spawn_consumer()
            threads.append(keeper)

    app['collector_threads'] = threads


async def stop_collect(app):
    logger.info('exiting')
    cos = []
    for thread in app['collector_threads']:
        cos.append(thread.kill())

    await asyncio.gather(*cos, loop=app.loop)


async def get_consumer_pairs_active(request):
    return aiohttp.web.json_response(
        dict(active_pairs=CONSUMER_PAIRS_ACTIVE),
        dumps=json_dumps
    )

async def get_consumer_pairs_status(request):
    rv = dict(
        status=dict([(consumer.consumer_id, consumer.get_status())
                    for consumer in request.app['collector_threads']])
    )
    return aiohttp.web.json_response(rv, dumps=json_dumps)


def main():
    loggers.setup()
    app = aiohttp.web.Application()
    app.on_startup.append(collect)
    app.on_cleanup.append(stop_collect)
    app.router.add_get('/', get_consumer_pairs_active)
    app.router.add_get('/status', get_consumer_pairs_status)
    aiohttp.web.run_app(app, port=int(os.getenv('PORT', 5000)))


if __name__ == '__main__':
    main()
