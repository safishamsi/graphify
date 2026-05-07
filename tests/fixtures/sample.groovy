package com.nicklastrange.example

import com.nicklastrange.Processor
import com.nicklastrange.util.Helper

class SampleService {
    Processor processor

    SampleService(Processor processor) {
        this.processor = processor
    }

    String process(String input) {
        def result = processor.transform(input)
        return Helper.clean(result)
    }

    private void reset() {
        processor.reset()
    }
}
