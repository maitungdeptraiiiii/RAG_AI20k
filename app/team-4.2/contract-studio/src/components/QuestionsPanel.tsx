// Câu hỏi gợi ý của gói luật (report.questions): trả lời một câu chỉ chạy lại luật, không đọc lại hợp đồng.
type Question = {
  fact: string;
  question: string;
  guaranteed: number;
  possible: number;
  options: { value: unknown; label: string }[];
};

type Props = {
  questions: Question[];
  disabled?: boolean;
  onAnswer: (questionIndex: number, optionIndex: number) => void;
};

export function QuestionsPanel({ questions, disabled, onAnswer }: Props) {
  if (!questions.length) return null;
  return (
    <section
      aria-label="Câu hỏi gợi ý"
      className="border border-sky-200 bg-sky-50 rounded p-4 text-xs"
    >
      <h3 className="font-semibold text-sm">Câu hỏi gợi ý</h3>
      <p className="text-stone-500 mt-1">
        Trả lời để kết luận thêm một số mục. Chỉ chạy lại luật, không đọc lại hợp đồng.
      </p>
      <div className="mt-3 space-y-3">
        {questions.map((q, qi) => (
          <div key={q.fact}>
            <p>
              {q.question}{" "}
              <span className="text-stone-400">
                (giải quyết được{" "}
                {q.guaranteed === q.possible ? q.possible : `${q.guaranteed}–${q.possible}`} mục)
              </span>
            </p>
            <div className="flex flex-wrap gap-2 mt-1">
              {q.options.map((o, oi) => (
                <button
                  key={String(o.value)}
                  type="button"
                  disabled={disabled}
                  onClick={() => onAnswer(qi, oi)}
                  className="px-3 py-1 rounded border border-sky-300 bg-white hover:bg-sky-100 disabled:opacity-40 cursor-pointer"
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
