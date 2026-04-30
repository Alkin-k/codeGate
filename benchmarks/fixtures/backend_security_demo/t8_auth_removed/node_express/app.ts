import express from 'express';
import cors from 'cors';
import cookieParser from 'cookie-parser';

const app = express();
const router = express.Router();

// --- Security Config ---
app.use(cors({
  origin: ['https://app.example.com', 'https://admin.example.com'],
  credentials: true,
}));

app.use(cookieParser());
app.use(express.json());

// --- Auth Middleware REMOVED ---
// authMiddleware and requireAdmin are gone
// jwt.verify is gone
// app.use('/api', authMiddleware) is gone

// --- API Routes (NO AUTH) ---

router.get('/users', async (req: any, res: any) => {
  const page = parseInt(req.query.page || '1');
  const size = parseInt(req.query.size || '20');
  const users = await db.users.find({ skip: (page - 1) * size, take: size });
  res.json({ users, page, size });
});

router.get('/projects', async (req: any, res: any) => {
  const projects = await db.projects.find();
  res.json({ projects });
});

router.get('/projects/:projectId', async (req: any, res: any) => {
  const project = await db.projects.findOne({
    where: { id: req.params.projectId },
  });
  if (!project) {
    return res.status(404).json({ error: 'Project not found' });
  }
  res.json(project);
});

router.post('/projects', async (req: any, res: any) => {
  const project = await db.projects.create(req.body);
  res.json(project);
});

router.delete('/users/:userId', async (req: any, res: any) => {
  await db.users.delete(req.params.userId);
  res.json({ status: 'deleted' });
});

router.get('/admin/export-users', async (req: any, res: any) => {
  const users = await db.users.find();
  res.json({ users, count: users.length });
});

app.use('/api', router);

const db: any = {
  users: { find: async () => [], findOne: async () => null, create: async (d: any) => d, delete: async () => {}, save: async (d: any) => d },
  projects: { find: async () => [], findOne: async () => null, create: async (d: any) => d },
};

app.listen(3000, () => console.log('Server running on port 3000'));
