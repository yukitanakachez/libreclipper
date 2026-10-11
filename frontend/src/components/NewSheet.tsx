import { notifyChanged } from "../changes";
import { go } from "../route";
import Dialog from "./Dialog";
import NewJobForm from "./NewJobForm";

export default function NewSheet({ onClose }: { onClose: () => void }) {
  return (
    <Dialog title="New clip job" onClose={onClose} initialFocus="input, select, textarea">
      <NewJobForm onCreated={(id) => { go({ id }); notifyChanged(); onClose(); }} />
    </Dialog>
  );
}
