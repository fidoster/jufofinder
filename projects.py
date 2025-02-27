from flask import Blueprint, render_template, request, redirect, url_for, jsonify
import project_database
from database import get_history

projects_bp = Blueprint('projects', __name__, template_folder='templates')

@projects_bp.route('/projects')
def list_projects():
    projects = project_database.get_all_projects()
    return render_template('projects.html', projects=projects)

@projects_bp.route('/projects/new', methods=['GET', 'POST'])
def new_project():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        project_database.add_project(title, description)
        return redirect(url_for('projects.list_projects'))
    return render_template('project_form.html')

@projects_bp.route('/projects/<int:project_id>')
def project_detail(project_id):
    project = project_database.get_project(project_id)
    sections = project_database.get_sections(project_id)
    for section in sections:
        section['articles'] = project_database.get_articles(section['id'])
    history = get_history()
    available_searches = list({h['keywords'] for h in history if h.get('keywords')})
    return render_template('project_detail.html', project=project, sections=sections, available_searches=available_searches)

@projects_bp.route('/projects/<int:project_id>/delete', methods=['POST'])
def delete_project(project_id):
    project_database.delete_project(project_id)
    return redirect(url_for('projects.list_projects'))

@projects_bp.route('/projects/<int:project_id>/section/new', methods=['POST'])
def add_section(project_id):
    title = request.form.get('title')
    project_database.add_section(project_id, title)
    return redirect(url_for('projects.project_detail', project_id=project_id))

@projects_bp.route('/projects/section/<int:section_id>/delete', methods=['POST'])
def delete_section(section_id):
    project_id = project_database.get_project_id_by_section(section_id)
    project_database.delete_section(section_id)
    return redirect(url_for('projects.project_detail', project_id=project_id))

@projects_bp.route('/projects/<int:project_id>/section/<int:section_id>/search_block/new', methods=['POST'])
def add_search_block(project_id, section_id):
    keywords = request.form.get('keywords')
    success = project_database.add_search_block(section_id, keywords)
    if not success:
        return "Search not found in history", 404
    return redirect(url_for('projects.project_detail', project_id=project_id))

@projects_bp.route('/projects/<int:project_id>/section/<int:section_id>/article/<int:article_id>/delete', methods=['POST'])
def delete_article_route(project_id, section_id, article_id):
    project_database.delete_article(article_id)
    return redirect(url_for('projects.project_detail', project_id=project_id))

# NEW: Delete individual article from search block
@projects_bp.route('/projects/<int:project_id>/section/<int:section_id>/search_block/<int:block_id>/article/<int:article_index>/delete', methods=['POST'])
def delete_article_from_block(project_id, section_id, block_id, article_index):
    success = project_database.delete_article_from_block(block_id, article_index)
    return redirect(url_for('projects.project_detail', project_id=project_id))
