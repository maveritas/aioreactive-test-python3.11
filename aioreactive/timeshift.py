import asyncio
from datetime import datetime, timedelta
from typing import Tuple, TypeVar

from expression.core import MailboxProcessor, pipe
from expression.system import CancellationTokenSource

from .notification import Notification, OnError, OnNext
from .observables import AsyncAnonymousObservable
from .observers import AsyncNotificationObserver
from .types import AsyncDisposable, AsyncObservable, AsyncObserver, Stream

TSource = TypeVar("TSource")


def delay(seconds: float) -> Stream[TSource, TSource]:
    """Delay observable.

    Time shifts the observable sequence by the given timeout. The
    relative time intervals between the values are preserved.

    Args:
        seconds (float): Number of seconds to delay.

    Returns:
        Stream[TSource, TSource]: Delayed stream.
    """

    def _delay(source: AsyncObservable[TSource]) -> AsyncObservable[TSource]:
        cts = CancellationTokenSource()

        async def subscribe_async(aobv: AsyncObserver[TSource]) -> AsyncDisposable:
            async def worker(inbox: MailboxProcessor[Tuple[Notification, datetime]]) -> None:
                while True:
                    ns, due_time = await inbox.receive()

                    diff = due_time - datetime.utcnow()
                    seconds = diff.total_seconds()
                    if seconds > 0:
                        await asyncio.sleep(seconds)

                    if isinstance(ns, OnNext):
                        x = ns.value
                        await aobv.asend(x)
                    elif isinstance(ns, OnError):
                        err = ns.exception
                        await aobv.athrow(err)
                    else:
                        await aobv.aclose()

            agent = MailboxProcessor.start(worker, cts.token)

            async def fn(ns: Notification) -> None:
                due_time = datetime.utcnow() + timedelta(seconds=seconds)
                agent.post((ns, due_time))

            obv: AsyncNotificationObserver[TSource] = AsyncNotificationObserver(fn)
            subscription = await pipe(obv, source.subscribe_async)

            async def cancel() -> None:
                cts.cancel()
                await subscription.dispose_async()

            return AsyncDisposable.create(cancel)

        return AsyncAnonymousObservable(subscribe_async)

    return _delay
