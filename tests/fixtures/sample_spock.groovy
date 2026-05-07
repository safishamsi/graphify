package com.nicklastrange.example

import spock.lang.Specification

class SampleSpec extends Specification {

    def setup() {
        // common setup
    }

    def "should process valid input"() {
        given:
        def input = "hello"

        when:
        def result = input.toUpperCase()

        then:
        result == "HELLO"
    }

    def "should not change value when it's already correct"() {
        given:
        def value = "HELLO"

        when:
        def result = value.toUpperCase()

        then:
        result == value
    }

    def "should handle #input and return #expected"() {
        expect:
        input.toUpperCase() == expected

        where:
        input   | expected
        "hello" | "HELLO"
        "world" | "WORLD"
    }
}
