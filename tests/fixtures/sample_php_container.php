<?php

namespace App\Providers;

class PaymentGateway {}
class StripeGateway {}
class CashierGateway {}

class AppServiceProvider
{
    public function register(): void
    {
        $this->app->bind(PaymentGateway::class, StripeGateway::class);
        $this->app->singleton(CashierGateway::class, StripeGateway::class);
    }
}
