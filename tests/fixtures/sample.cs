using System;
using System.Collections.Generic;
using System.Net.Http;

namespace GraphifyDemo
{
    public interface IProcessor
    {
        List<string> Process(List<string> items);
    }

    public class Processor
    {
    }

    public class Result<T>
    {
    }

    public class DataProcessor : Processor, IProcessor
    {
        private readonly HttpClient _client;

        public DataProcessor()
        {
            _client = new HttpClient();
        }

        public List<string> Process(List<string> items)
        {
            return Validate(items);
        }

        public Result<DataProcessor> Build(HttpClient client)
        {
            return null;
        }

        private List<string> Validate(List<string> items)
        {
            var result = new List<string>();
            foreach (var item in items)
            {
                if (!string.IsNullOrEmpty(item))
                    result.Add(item.Trim());
            }
            return result;
        }
    }
}
