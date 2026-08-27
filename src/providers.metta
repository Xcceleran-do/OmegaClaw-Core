(= (llmProviderStart $provider)
   (py-call (providers.llmProviderStart $provider)))

(= (llmProviderChat $prompt $max_tokens $reasoning_mode)
   (py-call (providers.llmProviderChat $prompt $max_tokens $reasoning_mode)))

(= (llmProviderContextChat $prompt $skills $extensions $output_format $memory_dir $task_message $user_message $time $history $context_window_tokens $max_output_tokens $reasoning_mode)
   (py-call (providers.llmProviderContextChat $prompt $skills $extensions $output_format $memory_dir $task_message $user_message $time $history $context_window_tokens $max_output_tokens $reasoning_mode)))
