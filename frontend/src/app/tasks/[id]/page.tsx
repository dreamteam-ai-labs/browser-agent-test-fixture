"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Image from "next/image";
import Layout from "@/components/Layout";
import api from "@/lib/api";

interface Task {
  id: number;
  title: string;
  description: string;
  status: string;
  project_id: number | null;
  assignee_id: number | null;
  url: string | null;
  preview_url: string | null;
}

interface Project {
  id: number;
  name: string;
}

export default function TaskDetailPage() {
  const params = useParams();
  const router = useRouter();
  const [task, setTask] = useState<Task | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState("pending");
  const [projectId, setProjectId] = useState<string>("");
  const [url, setUrl] = useState("");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [captureError, setCaptureError] = useState("");

  useEffect(() => {
    api.get(`/api/tasks/${params.id}`).then((res) => {
      const t = res.data as Task;
      setTask(t);
      setTitle(t.title);
      setDescription(t.description || "");
      setStatus(t.status || "pending");
      setProjectId(t.project_id ? String(t.project_id) : "");
      setUrl(t.url || "");
      setPreviewUrl(t.preview_url || null);
    });
    api.get("/api/projects").then((res) => setProjects(res.data));
  }, [params.id]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const updated = await api.put(`/api/tasks/${params.id}`, {
        title,
        description,
        status,
        project_id: projectId ? parseInt(projectId) : null,
        url: url || null,
      });
      setTask(updated.data);
      setPreviewUrl(updated.data.preview_url || null);
      router.push("/tasks");
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e.response?.data?.detail || "Failed to update task");
    } finally {
      setSaving(false);
    }
  };

  const handleCapturePreview = async () => {
    setCapturing(true);
    setCaptureError("");
    try {
      const res = await api.post(`/api/tasks/${params.id}/preview`);
      setPreviewUrl(res.data.preview_url);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setCaptureError(e.response?.data?.detail || "Failed to capture preview");
    } finally {
      setCapturing(false);
    }
  };

  if (!task) return <Layout><div className="p-8 text-gray-500">Loading...</div></Layout>;

  return (
    <Layout>
      <div className="max-w-lg">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Edit Task</h1>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSave} className="space-y-4">
          <div>
            <label htmlFor="title" className="block text-sm font-medium text-gray-700 mb-1">Title</label>
            <input
              id="title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
            />
          </div>

          <div>
            <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              id="description"
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
            />
          </div>

          <div>
            <label htmlFor="project_id" className="block text-sm font-medium text-gray-700 mb-1">Project</label>
            <select
              id="project_id"
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
            >
              <option value="">No project</option>
              {projects.map((p) => (
                <option key={p.id} value={String(p.id)}>{p.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="status" className="block text-sm font-medium text-gray-700 mb-1">Status</label>
            <select
              id="status"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
            >
              <option value="pending">Pending</option>
              <option value="in_progress">In Progress</option>
              <option value="done">Done</option>
            </select>
          </div>

          <div>
            <label htmlFor="url" className="block text-sm font-medium text-gray-700 mb-1">
              URL (for browser preview)
            </label>
            <input
              id="url"
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
              placeholder="https://example.com"
            />
          </div>

          <div className="flex gap-3">
            <button
              type="submit"
              disabled={saving}
              className="flex-1 py-2 px-4 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {saving ? "Saving..." : "Save Changes"}
            </button>
            <button
              type="button"
              onClick={() => router.push("/tasks")}
              className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>

        {/* URL Preview Section */}
        <div className="mt-8 border-t border-gray-200 pt-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">URL Preview</h2>

          {url ? (
            <button
              type="button"
              onClick={handleCapturePreview}
              disabled={capturing}
              className="px-4 py-2 bg-purple-600 text-white font-medium rounded-lg hover:bg-purple-700 disabled:opacity-50 transition-colors mb-4"
            >
              {capturing ? "Capturing..." : "Capture Preview"}
            </button>
          ) : (
            <p className="text-sm text-gray-500 mb-4">Add a URL above to enable preview capture.</p>
          )}

          {captureError && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">
              {captureError}
            </div>
          )}

          {previewUrl ? (
            <div className="border border-gray-200 rounded-lg overflow-hidden">
              <p className="text-xs text-gray-500 px-3 py-2 bg-gray-50 border-b border-gray-200 truncate">
                {previewUrl}
              </p>
              <Image
                src={previewUrl}
                alt="URL preview screenshot"
                width={600}
                height={400}
                className="w-full object-cover"
                unoptimized
              />
            </div>
          ) : (
            <div className="border-2 border-dashed border-gray-200 rounded-lg p-8 text-center text-gray-400 text-sm">
              No preview captured yet
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}
