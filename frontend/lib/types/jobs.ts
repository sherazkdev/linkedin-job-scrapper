export type JobItem = {
  id: string;
  title: string;
  company: string | null;
  country_code: string | null;
  city: string | null;
  employment_type: string | null;
  is_remote: boolean | null;
  job_url: string | null;
  posted_at: string | null;
  location_text: string | null;
};

export type JobListResponse = {
  success: boolean;
  data: {
    items: JobItem[];
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
  };
};