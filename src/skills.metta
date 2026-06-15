(= (getSkills)
   (;INTERNAL:
    "- Remember a particular string such as skills and memories: remember string"
    "- Query long-term embedding memory for skills and memories with short phrases only: query string"
    "- Episodes searches history for episodes around a time stamp, time format is same as in TIME: episodes time_string"
    "- Pin a certain string as short-term working memory item to keep track of task state: pin string"
    ;SHELL AND FILE I/O:
    "- Execute shell command without apostrophe in string, it returns the command output to you: shell string"
    "- Read file to string: read-file filename"
    "- Write string to file: write-file filename string"
    "- Append line to file: append-file filename string",
    ;MINDPLEX:
    "- If asked to Generate article , draft it strictly using the editorial agent, without waiting user input for topic: write-article"
    "- Like write-article, but selects today's lead theme via NAL (Non-Axiomatic Logic) deduction and belief revision over the atomspace instead of the python heuristic: write-article-nal"
    ;COMMUNICATION CHANNELS:
    "- Send message to user: send string"
    "- Search the web: search string"
    "- Search the web using the Tavily Search Agent: tavily-search string"
    "- Get technical analysis for a stock ticker using the Technical Analysis Agent: technical-analysis ticker"
    ;CODE EXECUTION:
    "- Execute MeTTa expression: metta sexpression"
    "Example to invoke Non-Axiomatic Logic via MeTTa: "
    "metta (|- ((--> (× sam garfield) friend) (stv 1.0 0.9))"
    "          ((--> garfield animal) (stv 1.0 0.9)))"
    "metta (|- ((==> (--> (× $1 elephant) eat) (--> $1 ([] dangerous))) (stv 1.0 0.9))"
    "          ((--> (× tiger elephant) eat) (stv 1.0 0.9)))"
    "Also: note the $1 for independent variables, and for negated knowledge use (stv 0.0 0.9)"
    "Additionally |- also works for revision, to merge evidence even when the term of both premises is the same."
    "You can also use PLN:"
    "metta (|~ ((Implication (Inheritance $1 (IntSet Feathered))"
    "           (Inheritance $1 Bird)) (stv 1.0 0.9))"
    "          ((Inheritance Pingu (IntSet Feathered)) (stv 1.0 0.9)))"))


(= (read-file $file)
   (progn (translatePredicate (exists_file $file))
          (translatePredicate (read_file_to_string $file $content ()))
          $content))

(= (write-file $file $str)
   (progn (translatePredicate (open $file write $Out))
          (translatePredicate (write $Out $str))
          (translatePredicate (close $Out))
          WRITE-FILE-SUCCESS))

(= (append-file $file $str)
   (progn (translatePredicate (exists_file $file))
          (translatePredicate (open $file append $Out))
          (translatePredicate (write $Out $str))
          (translatePredicate (nl $Out)),
          (translatePredicate (close $Out))
          APPEND-FILE-SUCCESS))

(= (tavily-search $query)
   (py-call (agentverse.tavily_search $query)))

   
(= (send-ui $msg)
   (send $msg))


(= (technical-analysis $ticker)
   (py-call (agentverse.technical_analysis $ticker)))



;; write-article-nal: same as write-article, but selects today's lead
;; theme via NAL deduction/revision (lib_editorial_reasoning.metta)
;; instead of the Python score = signal*0.7 + history*0.3 heuristic.
;; 1. gather_theme_candidates() fetches sources and returns
;;    (ThemeSignal "<theme>" <signal> <history>) facts as a string.
;; 2. sread parses that string into an atomspace tuple.
;; 3. select-and-explain (lib_editorial_reasoning.metta) derives each
;;    theme's LeadCandidate belief and returns the winner plus a
;;    reasoning trace for every candidate.
;; 4. finish_nal_article drafts/critiques/publishes the winning theme
;;    and records it in memory, mirroring editorial_agent's tail end.
(= (write-article-nal)
   (let $candidates_str (py-call (agentverse.gather_theme_candidates))
     (let $candidates (sread $candidates_str)
       (let $reasoning (select-and-explain $candidates)
         (let $result (py-call (agentverse.finish_nal_article (repr $reasoning)))
           (progn (send-ui (repr $result))
                  $result))))))

!(import_prolog_functions_from_file (library OmegaClaw-Core ./src/skills.pl) (shell first_char gc read_file_tail))

(= (metta $str)
   (let $code (sread $str)
        (repr (swrite (eval $code)))))

(= (pin $x)
   PIN-SUCCESS)
