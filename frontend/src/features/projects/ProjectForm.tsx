import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { Button, Stack, Textarea, TextInput, Title } from "@mantine/core";
import { Callout } from "../../design";
import type { Failure, Outcome } from "./scope";
import type { Project } from "./keys";

interface Props {
  title: string;
  submitLabel: string;
  initial: { name: string; description: string };
  resetOnSuccess?: boolean;
  /** Heading level of the form title (keeps the document outline continuous). */
  headingOrder?: 2 | 3 | 4;
  submit: (values: { name: string; description: string }) => Promise<Outcome<Project>>;
  onSaved: (project: Project) => void;
}

const SAVED_VISIBLE_MS = 8000;

function failureText(error: Failure): string {
  if (error.code === "SESSION_TOKEN_INVALID") {
    return "Your local session was refreshed. Nothing was saved; submit again.";
  }
  return error.message;
}

export function ProjectForm({ title, submitLabel, initial, resetOnSuccess, headingOrder = 4, submit, onSaved }: Props) {
  const ids = useId();
  const nameRef = useRef<HTMLInputElement | null>(null);
  const [name, setName] = useState(initial.name);
  const [description, setDescription] = useState(initial.description);
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  // The confirmation is a transient status: it clears itself (screen readers announce it while shown).
  useEffect(() => {
    if (saved === null) return;
    const timer = window.setTimeout(() => setSaved(null), SAVED_VISIBLE_MS);
    return () => window.clearTimeout(timer);
  }, [saved]);

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
    <Stack gap="sm">
      <Title order={headingOrder} id={`${ids}-title`}>
        {title}
      </Title>
      <TextInput
        ref={nameRef}
        label="Name"
        value={name}
        maxLength={120}
        required
        withAsterisk={false}
        error={problem === "Name is required."}
        aria-describedby={problem ? `${ids}-problem` : undefined}
        onChange={(e) => setName(e.currentTarget.value)}
      />
      <Textarea
        label="Description (optional)"
        value={description}
        maxLength={4000}
        rows={3}
        onChange={(e) => setDescription(e.currentTarget.value)}
      />
      {problem && (
        <div id={`${ids}-problem`}>
          <Callout tone="danger" role="alert">
            <p>
              {problem}
              {requestId && <> Request ID: {requestId}</>}
            </p>
          </Callout>
        </div>
      )}
      <div>
        <Button type="submit" disabled={pending} aria-busy={pending}>
          {pending ? "Saving…" : submitLabel}
        </Button>
      </div>
      {saved && (
        <Callout tone="success" role="status">
          <p>{saved}</p>
        </Callout>
      )}
    </Stack>
    </form>
  );
}
