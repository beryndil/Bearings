/**
 * Memory-form validation helpers (item 2.10).
 *
 * Pulled out of :class:`MemoriesEditor` so the rules are reachable
 * from the unit tests without mounting the component, and so the
 * component file's ``<script module>`` block is reserved for
 * Svelte-specific exports (interfaces consumed inside the template).
 *
 * Validation mirrors the backend's
 * :class:`bearings.web.models.tags.TagMemoryIn` field bounds:
 *
 * * ``title`` — 1 to :data:`TAG_MEMORY_TITLE_MAX_LENGTH` chars
 *   (after trim);
 * * ``body`` — 1 to :data:`TAG_MEMORY_BODY_MAX_LENGTH` chars
 *   (after trim).
 *
 * The form blocks submit on client-side error so a 422 from the
 * server-side validator is unreachable through the form path.
 */
import {
  MEMORIES_STRINGS,
  TAG_MEMORY_BODY_MAX_LENGTH,
  TAG_MEMORY_TITLE_MAX_LENGTH,
} from "../../config";

/**
 * Field-level error map. ``null`` means "no error"; a string is the
 * presentation message to surface beside the offending input.
 */
export interface MemoryFormErrors {
  title: string | null;
  body: string | null;
}

/** Untrimmed form values straight from the input bindings. */
export interface MemoryFormValues {
  title: string;
  body: string;
}

/** Run the bounds checks; return one ``MemoryFormErrors`` map. */
export function validateMemoryForm(values: MemoryFormValues): MemoryFormErrors {
  const title = values.title.trim();
  const body = values.body.trim();
  let titleErr: string | null = null;
  let bodyErr: string | null = null;
  if (title.length === 0) {
    titleErr = MEMORIES_STRINGS.validationTitleRequired;
  } else if (title.length > TAG_MEMORY_TITLE_MAX_LENGTH) {
    titleErr = MEMORIES_STRINGS.validationTitleTooLong;
  }
  if (body.length === 0) {
    bodyErr = MEMORIES_STRINGS.validationBodyRequired;
  } else if (body.length > TAG_MEMORY_BODY_MAX_LENGTH) {
    bodyErr = MEMORIES_STRINGS.validationBodyTooLong;
  }
  return { title: titleErr, body: bodyErr };
}

/** ``true`` when neither field carries an error. */
export function isFormValid(errors: MemoryFormErrors): boolean {
  return errors.title === null && errors.body === null;
}
