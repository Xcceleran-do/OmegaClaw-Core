!(import! &self ./tests/lib/utils)
!(import! &self ../src/evidence.py)

!(py-call (evidence.reset))
!(py-call (evidence.append "result-a" 100))
!(py-call (evidence.append "result-b" 100))

!(test (contains-text (py-call (evidence.render)) "result-a") True)
!(test (contains-text (py-call (evidence.render)) "result-b") True)

!(py-call (evidence.reset))
!(test (py-call (len (py-call (evidence.render)))) 0)
