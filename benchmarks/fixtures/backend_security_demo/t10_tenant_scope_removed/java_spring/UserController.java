package com.example.projectapi.controller;

import com.example.projectapi.model.User;
import com.example.projectapi.model.Project;
import com.example.projectapi.repository.UserRepository;
import com.example.projectapi.repository.ProjectRepository;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import javax.validation.Valid;
import java.security.Principal;
import java.util.List;

/**
 * T10 scenario: Auth preserved but tenant scope REMOVED.
 * findByTenantId → findAll, findByIdAndTenantId → findById
 */
@RestController
@RequestMapping("/api")
public class UserController {

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private ProjectRepository projectRepository;

    @GetMapping("/users")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Page<User>> listUsers(
            @AuthenticationPrincipal Principal principal,
            Pageable pageable) {
        // TENANT SCOPE REMOVED: was findByTenantId
        Page<User> users = userRepository.findAll(pageable);
        return ResponseEntity.ok(users);
    }

    @GetMapping("/projects")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<List<Project>> listProjects(
            @AuthenticationPrincipal Principal principal) {
        // TENANT SCOPE REMOVED
        List<Project> projects = projectRepository.findAll();
        return ResponseEntity.ok(projects);
    }

    @GetMapping("/projects/{projectId}")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Project> getProject(
            @PathVariable String projectId,
            @AuthenticationPrincipal Principal principal) {
        // TENANT SCOPE REMOVED: was findByIdAndTenantId
        Project project = projectRepository.findById(projectId).orElse(null);
        if (project == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(project);
    }

    @PostMapping("/projects")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Project> createProject(
            @Valid @RequestBody Project project,
            @AuthenticationPrincipal Principal principal) {
        Project saved = projectRepository.save(project);
        return ResponseEntity.ok(saved);
    }

    @DeleteMapping("/users/{userId}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Void> deleteUser(
            @PathVariable String userId,
            @AuthenticationPrincipal Principal principal) {
        // TENANT SCOPE REMOVED
        userRepository.deleteById(userId);
        return ResponseEntity.ok().build();
    }

    @GetMapping("/admin/export-users")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<List<User>> exportUsers(
            @AuthenticationPrincipal Principal principal) {
        // TENANT SCOPE REMOVED
        List<User> users = userRepository.findAll();
        return ResponseEntity.ok(users);
    }
}
