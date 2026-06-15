;; ============================================================
;; Editorial methodology - NAL "house style" rules
;; ============================================================
;; This file is the editable knobs for story selection. Each rule is
;; a NAL implication (==>) carrying a truth value (stv frequency
;; confidence):
;;   - frequency  = how strongly the antecedent implies the
;;                  consequent (0..1)
;;   - confidence = how much the agent trusts that rule (0..1)
;;
;; Edit these numbers, or add new (==> ... ...) rules following the
;; same shape, to change how the agent weighs evidence when picking
;; today's lead story. No Python or lib_editorial_reasoning changes
;; are needed for tuning these values.

;; --- Evidence scaling ---------------------------------------------
;; A theme is treated as having "full" StrongSignal once it is
;; mentioned this many times across today's fetched sources.
(= (signal-scale) 4)

;; A theme is treated as "fully Recurring" once it has been selected
;; this many times in past cycles (see ThemeMention in
;; editorial_memory.metta).
(= (history-scale) 2)

;; --- Methodology rules ----------------------------------------------
;; Rule 1: a strong signal today is good evidence that a theme is a
;; lead candidate.
(= (rule-strong-signal)
   ((==> (--> $T StrongSignal) (--> $T LeadCandidate)) (stv 0.9 0.8)))

;; Rule 2: a theme that keeps recurring across cycles is also evidence
;; of a lead candidate, slightly weaker/less certain than a fresh
;; strong signal on its own.
(= (rule-recurring)
   ((==> (--> $T Recurring) (--> $T LeadCandidate)) (stv 0.7 0.6)))
