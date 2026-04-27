<?php

namespace App\Providers;

class UserRegistered {}
class OrderPlaced {}
class SendWelcomeEmail {}
class NotifyAdmins {}
class ShipOrder {}

class EventServiceProvider
{
    protected $listen = [
        UserRegistered::class => [
            SendWelcomeEmail::class,
            NotifyAdmins::class,
        ],
        OrderPlaced::class => [
            ShipOrder::class,
        ],
    ];
}
