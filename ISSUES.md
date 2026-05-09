Bash(cd /home/xfz/kb/graphify_kb && $(cat graphify-out/.graphify_python) -c "
      import json…)
  ⎿  Error: Exit code 1
     Traceback (most recent call last):
       File "<string>", line 10, in <module>
       File "/usr/lib/python3.11/collections/__init__.py", line 597, in __init__          
         self.update(iterable, **kwds)
       File "/usr/lib/python3.11/collections/__init__.py", line 688, in update                                                                                                
         _count_elements(self, iterable)
       File "<string>", line 10, in <genexpr>                                                                                                                                 
     NameError: name 'Path' is not defined                                                                                                                                  
     total_files: 179
