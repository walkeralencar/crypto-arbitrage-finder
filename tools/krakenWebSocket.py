from kraken_wsclient_py import kraken_wsclient_py as client
from sortedcontainers import SortedDict

# configurable parameters
orderbookDepthInSubscription = 10
consolidatedOrderbookDepth = 10

orderbooks = dict()

def processSnapshot(orderbook,entries):
    orderbook.update([(float(entry[0]), float(entry[1])) for entry in entries])

def getSnapshotTimestamp(orderbookA,orderbookB=[]):
    return max([float(entry[2]) for entry in orderbookA+orderbookB])

def processDelta(orderbook,entries):
    for entry in entries:
        if float(entry[1]) > 0:
            orderbook.update([(float(entry[0]), float(entry[1]))])
        else:
            try:
                orderbook.pop(float(entry[0]))
            except KeyError as e:
                print('Error: Kraken asked to remove price level that doesn''t exist')
                pass

def getTop(orderbook, itemCount = 3, reverse=False):
    entries = []
    sliceBegin = 0
    sliceEnd  = itemCount
    if reverse is True:
        sliceBegin = len(orderbook)-itemCount
        sliceEnd  = len(orderbook)

    for x in orderbook.islice(start=sliceBegin, stop=sliceEnd,reverse=reverse):
        entries.append([x,orderbook[x]])

    return entries

        
def krakenMessageHandler(message):
    # Is subscription confirmation message?
    if 'event' in message and 'status' in message and 'channelID' in message and 'pair' in message:
        # Was subscription successful?
        if message['event'] == 'subscriptionStatus' and message['status'] == 'subscribed':            
            channelID = message['channelID']
            # create orderbook data structure for trading pair
            orderbooks[channelID] = dict()
            orderbooks[channelID]['symbol'] = translateNamingFromStandardToKraken([message['pair']],reversed=True)[0]
            orderbooks[channelID]['asks'] = SortedDict()
            orderbooks[channelID]['bids'] = SortedDict()
            orderbooks[channelID]['timestamp'] = None
    
    
    # Orderbook message?
    if isinstance(message,list) is False:
        return

    channelID = message[0]
    for payload in message[1:]:
        # Process snapshot
        if 'as' in payload and 'bs' in payload:
            processSnapshot(orderbook=orderbooks[channelID]['asks'], entries=payload['as'])
            processSnapshot(orderbook=orderbooks[channelID]['bids'], entries=payload['bs'])
            orderbooks[channelID]['timestamp']=getSnapshotTimestamp(payload['as'], payload['bs'])*1e3
            return

        # Prodess deltas
        if 'a' in payload:
            processDelta(orderbook=orderbooks[channelID]['asks'],entries=payload['a'])
            orderbooks[channelID]['timestamp']=getSnapshotTimestamp(payload['a'])*1e3
        if 'b' in payload:
            processDelta(orderbook=orderbooks[channelID]['bids'],entries=payload['b'])
            orderbooks[channelID]['timestamp']=getSnapshotTimestamp(payload['b'])*1e3
    
    
    # Data conversion
    asks = getTop(orderbook=orderbooks[channelID]['asks'],itemCount=consolidatedOrderbookDepth)
    bids = getTop(orderbook=orderbooks[channelID]['bids'],itemCount=consolidatedOrderbookDepth,reverse=True)
    payload = {}
    payload['exchange'] = "kraken"
    payload['symbol'] = orderbooks[channelID]['symbol']
    payload['data'] = {}
    payload['data']['asks'] = asks
    payload['data']['bids'] = bids
    payload['timestamp'] = orderbooks[channelID]['timestamp']

    print(orderbooks[channelID]['symbol'] + " asks:"+str(asks)+", bids:"+str(bids) + " timestamp:"+str(payload['timestamp']))


krakenNamingMappings = [('BTC','XBT')]
def translateNamingFromStandardToKraken(symbolsList,reversed=False):
    translatedList = []
    for symbol in symbolsList:
        translatedSymbol = symbol
        for krakenNamingMapping in krakenNamingMappings:
            if reversed is False:
                translatedSymbol = translatedSymbol.replace(krakenNamingMapping[0],krakenNamingMapping[1])
            else:
                translatedSymbol = translatedSymbol.replace(krakenNamingMapping[1],krakenNamingMapping[0])
            translatedList.append(translatedSymbol)
    return translatedList

my_client = client.WssClient()
my_client.subscribe_public(
    subscription={
        'name': 'book',
        'depth': orderbookDepthInSubscription
    },
    #pair=translateNamingFromStandardToKraken(['BTC/USD']),
    pair=translateNamingFromStandardToKraken(['BTC/USD', 'BTC/EUR', 'BTC/USD', 'BCH/USD', 'XRP/USD', 'LTC/EUR','LTC/USD', 'ETH/BTC', 'BCH/BTC', 'XRP/BTC']),
    callback=krakenMessageHandler
)

my_client.start()