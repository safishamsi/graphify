<?php

namespace App\Http;

use App\Auth\Authenticator;
use App\Cache\CacheManager;

class ApiClient
{
    private string $baseUrl;
    private Authenticator $auth;

    public function __construct(string $baseUrl)
    {
        $this->baseUrl = $baseUrl;
        $this->auth = new Authenticator();
    }

    public function get(string $path): string
    {
        return $this->fetch($path, 'GET');
    }

    public function post(string $path, string $body): string
    {
        return $this->fetch($path, 'POST');
    }

    private function fetch(string $path, string $method): string
    {
        $token = $this->auth->getToken();
        return $method . ' ' . $this->baseUrl . $path;
    }
}

interface Loggable
{
    public function log(): void;
}

trait HasName
{
    public function getName(): string
    {
        return '';
    }
}

class BaseProcessor {}

class Result {}

class DataProcessor extends BaseProcessor implements Loggable
{
    use HasName;

    private Result $current;

    public function run(DataProcessor $input): Result
    {
        return new Result();
    }

    public function log(): void
    {
    }
}

function parseResponse(string $raw): array
{
    return json_decode($raw, true);
}
