;; ============================================================
;; Editorial reasoning - NAL-based story selection
;; ============================================================
;; This module replaces the old Python heuristic
;;   score = signal_strength * 0.7 + historical_mentions * 0.3
;; with genuine NAL term-logic deduction over the atomspace. The
;; methodology (which evidence matters, and how much to trust it)
;; lives in memory/methodology.metta and can be edited there without
;; touching this file.
;;
;; Pipeline, per theme:
;;   1. Python hands this module raw evidence counts:
;;        (ThemeSignal "<theme>" <signal_strength> <historical_mentions>)
;;   2. count->stv turns each count into a NAL truth value
;;      (stv frequency confidence): more evidence -> higher
;;      confidence, via Truth_w2c (evidence-weight -> confidence).
;;   3. Two facts are built per theme:
;;        ((--> (Concept Theme) StrongSignal) (stv f c))
;;        ((--> (Concept Theme) Recurring)    (stv f c))
;;   4. Each fact is combined with the matching methodology rule from
;;      memory/methodology.metta via Truth_Deduction (NAL-5
;;      deduction), yielding a LeadCandidate belief from each piece
;;      of evidence. The two beliefs are then merged with
;;      Truth_Revision (NAL belief revision) into one belief about
;;        (--> (Concept Theme) LeadCandidate)
;;   5. Truth_Expectation reduces each theme's LeadCandidate belief to
;;      a single ranking number; the theme with the highest
;;      expectation is returned, together with its full truth value
;;      so the reasoning can be logged/explained.

!(import! &self (library OmegaClaw-Core ./memory/methodology))

;; --- Accessors -------------------------------------------------------

;; tv-of: pull the truth value out of a (Statement TV) pair. Used to
;; destructure the result of a function call without the (let (a b)
;; (call ...) ...) multi-variable pattern, which the translator does
;; not order correctly when the value comes from a function call.
(= (tv-of ($stmt $tv)) $tv)

;; --- Evidence -> truth value ------------------------------------------

;; clamp01: NAL frequencies live in [0,1]; cap at 1.0.
(= (clamp01 $x) (if (> $x 1.0) 1.0 $x))

;; count->stv: turn a raw evidence count into (stv freq conf).
;; freq saturates at 1.0 once $count reaches $scale; confidence grows
;; with the amount of evidence (Truth_w2c: weight -> confidence).
;; With $count = 0 this yields (stv 0 0) - "no evidence either way".
(= (count->stv $count $scale)
   (stv (clamp01 (/ $count $scale)) (Truth_w2c $count)))

;; --- Per-theme facts ----------------------------------------------------

(= (strong-signal-fact $theme $signal)
   ((--> (Concept $theme) StrongSignal) (count->stv $signal (signal-scale))))

(= (recurring-fact $theme $history)
   ((--> (Concept $theme) Recurring) (count->stv $history (history-scale))))

;; --- Combining the two pieces of evidence ------------------------------

;; combine-tv: NAL belief revision (Truth_Revision) merges two beliefs
;; about the same statement into one, weighted by their confidences.
;; When BOTH inputs carry zero confidence ("no evidence either way"
;; from count->stv with count=0, propagated through Truth_Deduction
;; as 0.0), Truth_Revision's weight-of-evidence division is 0.0/0.0
;; and undefined, so that case is short-circuited to (stv 0.0 0.0)
;; directly - still "no evidence either way".
(= (combine-tv (stv $f1 0.0) (stv $f2 0.0)) (stv 0.0 0.0))
(= (combine-tv $t1 $t2) (Truth_Revision $t1 $t2))

;; derive-lead-candidate: deduce a LeadCandidate belief from each piece
;; of evidence (StrongSignal, Recurring) via the methodology rules,
;; then revise the two beliefs into one.
(= (derive-lead-candidate $theme $signal $history)
   (let $strong-tv (Truth_Deduction (tv-of (strong-signal-fact $theme $signal))
                                     (tv-of (rule-strong-signal)))
     (let $recurring-tv (Truth_Deduction (tv-of (recurring-fact $theme $history))
                                          (tv-of (rule-recurring)))
       ((--> (Concept $theme) LeadCandidate) (combine-tv $strong-tv $recurring-tv)))))

;; --- Ranking themes -------------------------------------------------------

;; theme-expectation: derive the LeadCandidate belief for a theme and
;; reduce it to a single ranking number via Truth_Expectation.
;; Returns (Theme Expectation TV) - the full belief is kept alongside
;; the ranking number so it can be explained/logged.
(= (theme-expectation (ThemeSignal $theme $signal $history))
   (let $lc (derive-lead-candidate $theme $signal $history)
     ($theme (Truth_Expectation (tv-of $lc)) (tv-of $lc))))

;; pick-better: fold step, keeps whichever candidate has the higher
;; expectation seen so far.
(= (pick-better $best $candidate)
   (let ($bt $be $btv) $best
     (let ($t $e $tv) $candidate
       (if (> $e $be) ($t $e $tv) ($bt $be $btv)))))

;; select-lead-theme: given a tuple of
;;   (ThemeSignal Theme SignalStrength HistoricalMentions)
;; facts, derive every theme's LeadCandidate belief and return the
;; overall winner as (Theme Expectation TV).
(= (select-lead-theme $candidates)
   (foldl-atom (map-atom $candidates theme-expectation)
               (NoTheme -1.0 (stv 0.0 0.0))
               pick-better))

;; --- Explaining the reasoning ----------------------------------------------

;; explain-theme: human-readable trace for one theme, useful for
;; logging/inclusion in the article's reasoning notes.
(= (explain-theme (ThemeSignal $theme $signal $history))
   (let $lc (derive-lead-candidate $theme $signal $history)
     (ThemeReasoning $theme
                      (StrongSignalEvidence $signal)
                      (RecurringEvidence $history)
                      (LeadCandidateBelief (tv-of $lc))
                      (Expectation (Truth_Expectation (tv-of $lc))))))

(= (explain-candidates $candidates)
   (map-atom $candidates explain-theme))

;; --- Single entry point for Python --------------------------------------

;; select-and-explain: the ONE function the agent loop should call per
;; editorial cycle. It returns
;;   ((WinnerTheme WinnerExpectation WinnerTV) (ThemeReasoning ...)*)
;; i.e. the winning theme together with the full reasoning trace for
;; every candidate (for logging in the article's reasoning notes).
;;
;; Bundling everything into one function call/one top-level query is
;; deliberate: issuing select-lead-theme and explain-candidates as two
;; separate top-level queries against the same atomspace can leave the
;; second query unable to find solutions, so callers (agentverse.py)
;; must make a single call to this function per cycle.
(= (select-and-explain $candidates)
   ((select-lead-theme $candidates) (explain-candidates $candidates)))
