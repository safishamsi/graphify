<?php

namespace App\Support;

class Throttle
{
    public const int DEFAULT_PER_SECOND = 60;
    public const int DEFAULT_PER_DAY = 10000;
}

class RateLimiter
{
    public function perSecond(): int
    {
        return (int) config('throttle.api.per_second', 60);
    }

    public function perDay(): int
    {
        return (int) config('throttle.api.per_day', 10000);
    }
}
