package com.example.sample;

import com.example.base.Animal;
import com.example.contracts.Runnable;
import com.example.contracts.Swimmable;

public class Dog extends Animal implements Runnable, Swimmable {
    public void run() {}
    public void swim() {}
}

interface LoudRunnable extends Runnable {
    default void bark() {}
}
