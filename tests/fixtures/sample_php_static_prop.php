<?php

namespace App\Theme;

class DefaultPalette
{
    public static string $primary = '#3366ff';
    public static string $accent = '#ff6633';
}

class ColorResolver
{
    public function primary(): string
    {
        return DefaultPalette::$primary;
    }

    public function accent(): string
    {
        return DefaultPalette::$accent;
    }
}
