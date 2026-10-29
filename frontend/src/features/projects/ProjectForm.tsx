import { useId, useRef, useState, type FormEvent } from "react";
import type { Failure, Outcome } from "./scope";
import type { Project } from "./keys";

interface Props {
  title: string;
  submitLabel: string;
  initial: { name: string; description: string };
  resetOnSuccess?: boolean;
  submit: (values: { name: string; description: string }) => Promise<Outcome<Project>>;
  onSaved: (project: Project) => void;
}

function failureText(error: Failure): string {
  if (error.code === "SESSION_TOKEN_INVALID") {
    return "Your local session was refreshed. Nothing was saved; submit again.";
  }
  return error.message;
}

export function ProjectForm({ title, submitLabel, initial, resetOnSuccess, submit, onSaved }: Props) {
  const ids = useId();
  const nameRef = useRef<HTMLInputElement | null>(null);
  const [name, setName] = useState(initial.name);
  const [description, setDescription] = useState(initial.description);
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSaved(null);
    setRequestId(null);
    if (name.trim() === "") {
      setProblem("Name is required.");
      nameRef.current?.focus();
      return;
    }
    setProblem(null);
    setPending(true);
    const outcome = await submit({ name: name.trim(), description });
    if (outcome.status === "stale") return; // context changed: this form is gone or obsolete
    setPending(false);
    if (outcome.status === "error") {
      setProblem(failureText(outcome.error)); // entered values stay; stored values are untouched
      setRequestId(outcome.error.requestId);
      return;
    }
    setSaved(`Saved “${outcome.value.name}”.`);
    if (resetOnSuccess) {
      setName("");
      setDescription("");
    } else {
      setName(outcome.value.name);
      setDescription(outcome.value.description);
    }
    onSaved(outcome.value);
  }

  return (
    <form onSubmit={(e) => void onSubmit(e)} noValidate aria-labelledby={`${ids}-title`}>
      <h4 id={`${ids}-title`}>{title}</h4>
      <div className="field">
        <label htmlFor={`${ids}-name`}>Name</label>
        <input
          id={`${ids}-name`}
          ref={nameRef}
          value={name}
          maxLength={120}
          required
          aria-invalid={problem === "Name is required."}
          aria-describedby={problem ? `${ids}-problem` : undefined}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor={`${ids}-description`}>Description (optional)</label>
        <textarea
          id={`${ids}-description`}
          value={description}
          maxLength={4000}
          rows={3}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      {problem && (
        <p id={`${ids}-problem`} role="alert">
          {problem}
          {requestId && <> Request ID: {requestId}</>}
        </p>
      )}
      <button type="submit" disabled={pending} aria-busy={pending}>
        {pending ? "Saving…" : submitLabel}
      </button>
      {saved && <p role="status">{saved}</p>}
    </form>
  );
}
